import logging
from operator import itemgetter
import warnings
from typing import OrderedDict, Tuple

import torch
from torch import nn
import torch.nn.functional as F
from gensim.summarization.bm25 import BM25
from torchtext.data import TabularDataset

import ncn.core
from ncn.core import BaseData, Ints
from ncn.model import NeuralCitationNetwork

logger = logging.getLogger("neural_citation.inference")


# TODO: Document this
# TODO: Refactor this
class Evaluator:
    def __init__(self, weights, data: BaseData, eval: bool = True):
        self.data = data
        self.context, self.title, self.authors = self.data.cntxt, self.data.ttl, self.data.aut
        pad = self.title.vocab.stoi['<pad>']
        self.criterion = nn.CrossEntropyLoss(ignore_index = pad, reduction="sum")

        # instantiating model like this is bad, pass as params?
        self.model = NeuralCitationNetwork(context_filters=[4,4,5], context_vocab_size=len(self.context.vocab),
                                authors=True, author_filters=[1,2], author_vocab_size=len(self.authors.vocab),
                                title_vocab_size=len(self.title.vocab), pad_idx=pad, num_layers=2)

        # instantiate examples, corpus and bm25 depending on mode
        logger.info(f"Creating corpus in eval={eval} mode.")
        if eval:
            self.examples = data.test.examples
            logger.info(f"Number of samples in corpus: {len(self.examples)}")
            self.corpus = [example.title_cited for example in examples]
            self.bm25 = BM25(corpus)
        else:
            self.examples = data.train.examples + data.train.examples+ data.train.examples
            logger.info(f"Number of samples in corpus: {len(self.examples)}")
            self.corpus = [example.title_cited for example in examples]
            self.bm25 = BM25(corpus)

    def _get_bm_top(self, query: str) -> List[Tuple[float, str]]:
        q = self.context.tokenize(query)

        # sort titles according to score and return indices
        scores = [
            (score, index) for score, index in enumerate(bm25.get_scores(q))
            if bm25.get_score(q, index) > 0
        ]
        scores = sorted(scores, key=itemgetter(0), reverse=True)
        try:
            return [index for _, index in scores][:2048]
        except IndexError:
            return [index for _, index in scores]

    # TODO: get top 2048, pass through ncn for a single context, rerank according to ncn scores
    # Then evaluate if rerank is in top x, compute and return total score
    # Check if it's single int or list of ints and act accordingly
    def recall(self, x: Ints):
        if not eval: warnings.warn("Performing evaluation on all data. This hurts performance.", RuntimeWarning)
        
        if isinstance(x, int):
            for example in self.data.test:
                context = self.context.numericalize([example.context])
                citing = self.context.numericalize([example.authors_citing])
                indices = self._get_bm_top(example.context)
                # get titles, cited authors with top indices, pad and numericalize (see notebook)

                # repeat context and citing to len(indices) and calculate loss for single, large batch

        elif isinstance(x, list):
            for at_x in x:
                pass
        

    # TODO: For a query return the best citation context. Need to preprocess with context field first
    def recommend(self, query: str, top_x: int):
        if eval: warnings.warn("Performing inference only on the test set.", RuntimeWarning)
        q = self.data.cntxt.tokenize(query)
        # get indices
        # return top x