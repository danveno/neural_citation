import math
import time
import random
import logging
from pathlib import Path
from datetime import datetime
from tqdm import tqdm

import torch
from torch import nn
from torch import optim
import torch.nn.functional as F
import torch.nn.init as init
from torch.utils.tensorboard import SummaryWriter
from torchtext.data import BucketIterator

import core
from core import DEVICE, SEED, PathOrStr
from data_utils import generate_bucketized_iterators
from model import NeuralCitationNetwork

logger = logging.getLogger("neural_citation.train")


def init_weights(m):
    if isinstance(m, nn.Conv2d):
        init.kaiming_uniform_(m.weight, a=0, nonlinearity="relu")
    # TODO: Figure out how to initialize recurrent layers
    elif isinstance(m, nn.GRU) or isinstance(m, nn.LSTM):
        for w in m.all_weights:
            init.orthogonal_(w)
    elif isinstance(m, nn.Linear):
        init.xavier_uniform_(m.weight)

# FIXME: properly unpack training data
# TODO: Document this
def train(model, iterator, optimizer, criterion, clip):
    
    model.train()
    
    epoch_loss = 0
    
    for i, batch in enumerate(iterator):
        
        src = batch.src
        trg = batch.trg
        
        optimizer.zero_grad()
        
        output = model(src, trg)
        
        #trg = [trg sent len, batch size]
        #output = [trg sent len, batch size, output dim]
        
        output = output[1:].view(-1, output.shape[-1])
        trg = trg[1:].view(-1)
        
        #trg = [(trg sent len - 1) * batch size]
        #output = [(trg sent len - 1) * batch size, output dim]
        
        loss = criterion(output, trg)
        
        loss.backward()
        
        torch.nn.utils.clip_grad_norm_(model.parameters(), clip)
        
        optimizer.step()
        
        epoch_loss += loss.item()
        
    return epoch_loss / len(iterator)

# FIXME: properly unpack valid data
# TODO: Document this
def evaluate(model, iterator, criterion):
    
    model.eval()
    
    epoch_loss = 0
    
    with torch.no_grad():
    
        for i, batch in enumerate(iterator):

            src = batch.src
            trg = batch.trg

            output = model(src, trg, 0) #turn off teacher forcing

            #trg = [trg sent len, batch size]
            #output = [trg sent len, batch size, output dim]

            output = output[1:].view(-1, output.shape[-1])
            trg = trg[1:].view(-1)

            #trg = [(trg sent len - 1) * batch size]
            #output = [(trg sent len - 1) * batch size, output dim]

            loss = criterion(output, trg)

            epoch_loss += loss.item()
        
    return epoch_loss / len(iterator)


def train_ncn(model: nn.Module, train_iterator: BucketIterator, valid_iterator: BucketIterator, 
              n_epochs: int = 10, clip: int = 5, 
              save_dir: PathOrStr = "./models"):
    
    optimizer = optim.Adam(model.parameters(), lr=0.01)
    criterion = nn.CrossEntropyLoss(ignore_index = PAD_IDX, reduction="sum")

    best_valid_loss = float('inf')

    # set up tensorboard and data logging
    date = datetime.now()
    log_dir = Path(f"runs/{date.year}_NCN_{date.month}_{date.day}_{date.hour}")
    writer = SummaryWriter(log_dir=log_dir)

    for epoch in range(n_epochs):
        
        
        train_loss = train(model, train_iterator, optimizer, criterion, clip)
        valid_loss = evaluate(model, valid_iterator, criterion)

        writer.add_scalar('loss/training', train_loss)
        writer.add_scalar('loss/validation', valid_loss)
        
        if valid_loss < best_valid_loss:
            best_valid_loss = valid_loss
            if not save_dir.exists(): save_dir.mkdir()
            torch.save(model.state_dict(), save_dir/f"NCN_{date.month}_{date.day}_{date.hour}.pt")


if __name__ == '__main__':
    # Set the random seeds before training
    random.seed(SEED)
    torch.manual_seed(SEED)
    torch.backends.cudnn.deterministic = True

    # set up training
    data = generate_bucketized_iterators("/home/timo/DataSets/KD_arxiv_CS/arxiv_data.csv")
    PAD_IDX = data.ttl.vocab.stoi['<pad>']
    cntxt_vocab_len = len(data.cntxt.vocab)
    aut_vocab_len = len(data.aut.vocab)
    ttl_vocab_len = len(data.ttl.vocab)
    

    net = NeuralCitationNetwork(context_filters=[4,4,5], context_vocab_size=cntxt_vocab_len,
                                authors=True, author_filters=[1,2], author_vocab_size=aut_vocab_len,
                                title_vocab_size=ttl_vocab_len, pad_idx=PAD_IDX, num_layers=2)
    net.apply(init_weights)

    train_ncn(net, data.train_iter, data.valid_iter)
