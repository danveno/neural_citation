import torch
from torch import nn
import torch.nn.functional as F
from typing import List

Filters = List[int]

class TDNN(nn.Module):
    """
    Single TDNN Block for the neural citation network.
    Implementation is based on:  
    https://ronan.collobert.com/pub/matos/2008_nlp_icml.pdf.  
    Consists of the following layers (in order): Convolution, Batchnorm, ReLu, MaxPool.  

    **Parameters**:   

    - *filter_size* (int): filter length for the convolutional operation  
    - *embed_size* (int): Dimension of the input word embeddings  
    - *num_filters* (int=64): Number of convolutional filters  

    **Input**:  

    - *Tensor* of shape: [N: batch size, D: embedding dimensions, L: sequence length].  

    **Output**:  

    - *Tensor* of shape: [batch_size, num_filters]. 
    """

    def __init__(self, filter_size: int, embed_size: int, num_filters: int = 64):
        super().__init__()
        # model input shape: [N: batch size, D: embedding dimensions, L: sequence length]
        self.conv = nn.Conv2d(1, num_filters, kernel_size=(embed_size, filter_size))
        self.bn = nn.BatchNorm2d(num_filters)

    def forward(self, x):
        """
        Forward pass.
        """
        # output shape: [N: batch size, 1: channels, D: embedding dimensions, L: sequence length]
        x = x.unsqueeze(1)


        # output shape: batch_size, num_filters, 1, f(seq length)
        x = F.relu(self.bn(self.conv(x)))
        pool_size = x.shape[-1]

        # output shape: batch_size, num_filters, 1, 1
        x = F.max_pool2d(x, kernel_size=pool_size)

        # output shape: batch_size, 1, num_filters, 1
        return torch.einsum("nchw -> nhcw", x)


# Pad all sequences to equal length so the attention mechanism work -> We don't need this
# Why do we nee an encoder and decoder Embedding?
# Because even though we use English as language for input and output,
# the words used are in the contexts and the cited paper's titles.
# This is especially pronounced when using a small vocabulary (like 20k words).
# TODO: Define min and max length based on data -> We need only the max and we don't need to pad :)
# TODO: Check how we can get only the last relevant output
# TODO: Implement bucketing to avoid excess computation due to 0 padding -> We don't need that
# TODO: Masking the loss function??? Why??


class AttnDecoderRNN(nn.Module):
    """
    Decoder module for a seq2seq model. The implementation is based on the PyTorch documentation.
    The original code can be found here:  
    https://pytorch.org/tutorials/intermediate/seq2seq_translation_tutorial.html.  
    Background: https://arxiv.org/pdf/1409.0473.pdf.  
    
    **Parameters**:  
    
    - *param1* (type):  
    
    **Input**:  
    
    - Input 1: [shapes]  
    
    **Output**:  
    
    - Output 1: [shapes]  
    """
    def __init__(self, hidden_size: int, output_size: int, dropout_p=0.2, max_length: int = 20):
        super().__init__()
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.dropout_p = dropout_p
        self.max_length = max_length
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.embedding = nn.Embedding(self.output_size, self.hidden_size)
        self.attn = nn.Linear(self.hidden_size * 2, self.max_length)
        self.attn_combine = nn.Linear(self.hidden_size * 2, self.hidden_size)
        self.dropout = nn.Dropout(self.dropout_p)
        self.gru = nn.GRU(self.hidden_size, self.hidden_size)
        self.out = nn.Linear(self.hidden_size, self.output_size)

    def forward(self, input, hidden, encoder_outputs):
        embedded = self.embedding(input).view(1, 1, -1)
        embedded = self.dropout(embedded)

        attn_weights = F.softmax(
            self.attn(torch.cat((embedded[0], hidden[0]), 1)), dim=1)
        attn_applied = torch.bmm(attn_weights.unsqueeze(0),
                                 encoder_outputs.unsqueeze(0))

        output = torch.cat((embedded[0], attn_applied[0]), 1)
        output = self.attn_combine(output).unsqueeze(0)

        output = F.relu(output)
        output, hidden = self.gru(output, hidden)

        output = F.log_softmax(self.out(output[0]), dim=1)
        return output, hidden, attn_weights

    def initHidden(self):
        return torch.zeros(1, 1, self.hidden_size, device=self._device)



class NCN(nn.Module):
    """
    PyTorch implementation of the neural citation network by Ebesu & Fang.  
    The original paper can be found here:  
    http://www.cse.scu.edu/~yfang/NCN.pdf.   
    The author's tensorflow code is on github:  
    https://github.com/tebesu/NeuralCitationNetwork.  

    **Parameters**:  
    
    - *num_filters* (int=64): Number of filters applied in the TDNN layers of the model.  
    - *authors* (bool=False): Use additional author information or not.  
    - *w_emebd_size* (int=300): Input word embedding dimensions.  
    - *num_layers* (int=1): Number of RNN layers.  
    - *hidden_dims* (int=64): Dimension of the RNN hidden states.  
    - *batch_size* (int=32): Training batch size.  
    
    **Input**:  
    
    - *Tensor* of shape: [N: batch size, D: embedding dimensions, L: sequence length].   
    
    **Output**:  
    
    - Output 1: [shapes] 
    """
    def __init__(self, filters: Filters,
                       num_filters: int = 64,
                       authors: bool = False, 
                       w_embed_size: int = 300,
                       num_layers: int = 1,
                       hidden_dims: int = 64,
                       batch_size: int = 32):
        super().__init__()

        self.use_authors = authors
        self.filter_list = filters
        self.num_filters = num_filters
        self.bs = 32
        self._num_filters_total = len(filters)*num_filters
        
        # context encoder
        self.context_encoder = [TDNN(filter_size=f, embed_size = w_embed_size, num_filters=num_filters) 
                                for f in self.filter_list]
        
        # Are inputs and outputs here really right?
        self.fc = nn.Linear(self._num_filters_total, self._num_filters_total)

        if self.use_authors:
            # author encoder

            # author decoder
            pass

        # decoder

    def forward(self, x):
        # encoder
        # output: List of tensors w. shape: batch size, 1, num_filters, 1
        x = [encoder(x) for encoder in self.context_encoder]
        # output shape: batch_size, list_length, num_filters
        x = torch.cat(x, dim=1).squeeze()
        # output shape: batch_size, list_length*num_filters
        x = x.view(self._bs, -1)

        # apply nonlinear mapping
        x = torch.tanh(self.fc(x))
        x = x.view(-1, len(self._filter_list), self.num_filters)

        #------------------------------------------------------------------
        # decode

        return x
