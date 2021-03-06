import collections
import gzip
import itertools
import json
import re
from operator import itemgetter

import nltk.stem, nltk.corpus
import wget
from gensim import corpora, models, similarities


#try:
#    stopwords = set(nltk.corpus.stopwords.words('english'))
#except LookupError:
#    nltk.download('stopwords')
stopwords = set(nltk.corpus.stopwords.words('english'))
stemmer = nltk.stem.snowball.SnowballStemmer('english')

LIBRARY = 'card_commander_library.json.gz'
DICTIONARY = 'card_text_dictionary.dict'
CORPUS = 'card_text_corpus.mm'
INDEX = 'card_text_lsi.index'
TFIDF = 'card_text_tfidf.model'
LSI = 'card_text_lsi.model'


class Similaritron(object):
    # TODO: num_topics is a magic number?
    def __init__(self):
        print('Loading models...')
        self.dictionary = corpora.Dictionary.load(DICTIONARY)
        # self.corpus = corpora.MmCorpus(CORPUS)
        self.index = similarities.MatrixSimilarity.load(INDEX)
        self.tfidf = models.TfidfModel.load(TFIDF)
        self.lsi = models.LsiModel.load(LSI)

        self.cards = json.load(gzip.open(LIBRARY, 'rt'))
        self._card_index = {self._normalize_card_name(c['name']):idx
                            for idx, c in enumerate(self.cards)}
        print('\t...done.')

    def _normalize_card_name(self, name):
        name = name.lower()
        name = re.sub('[^a-z0-9]','', name)
        return name

    def _similarity(self, card):
        vec_bow = self.dictionary.doc2bow(tokenize(card))
        vec_lsi = self.lsi[self.tfidf[vec_bow]]
        scores = self.index[vec_lsi]
        return sorted(enumerate(scores),
                key=itemgetter(1), reverse=True)

    def get_card_by_name(self, name):
        return self.cards[self._card_index[self._normalize_card_name(name)]]

    def get_similar_cards(self, target_card_name, N=10, offset=0):
        target_card = self.get_card_by_name(target_card_name)
        similarity_scores = self._similarity(target_card)
        similar_cards = []
        for card_idx, score in similarity_scores:
            this_card = self.cards[card_idx]
            is_same_card = (self._normalize_card_name(this_card['name']) ==
                            self._normalize_card_name(target_card_name))
            # Exclude identical and vanilla cards
            if not is_same_card and this_card.get('text'):
                similar_cards.append(this_card)
            if len(similar_cards) >= N + offset:
                break
        return similar_cards[offset:]


def tokenize(card):
    text = ' '.join([card.get('text', '')]
                   # + card.get('types', [])
                   + card.get('subtypes', [])
                    )
    text = text.lower()
    ## Replace card name with ~
    text = text.replace(card['name'].lower(), '~')
    ## remove reminder text (in parentheses)
    text = re.sub(r'\([^)]+\)', '', text)
    ## remove costs
    text = re.sub(r'\{[^}]+\}', '', text)
    ## genericize all p/t (de)buffs
    text = re.sub(r'([+-])[\dX*]/([+-])[\dX*]', r'\1X/\2X', text)
    ## genericize numbers
    text = re.sub(r'\d+', 'N', text)
    ## split on punctuation and spaces
    tokens = re.split(r'[\s.,;:—()]+', text)
    # use only unique tokens?
    # tokens = set(tokens)
    # stem tokens
    stopwords = set(nltk.corpus.stopwords.words('english'))
    tokens = (stemmer.stem(t) for t in tokens if t and t not in stopwords)

    ## The following allows us to singularize certain terms.
    ## For example, the word 'equip' is way over-represented on equipment
    counter = collections.Counter(tokens)
    if counter['equip']:
        counter['equip'] = 1

    tokens = itertools.chain.from_iterable([token] * count for token, count in counter.items())

    return list(tokens)


if __name__ == '__main__':
    cards = json.load(gzip.open(LIBRARY, 'rt'))

    card_names = [c['name'] for c in cards]

    # nltk.download('stopwords')
    # stopwords = set(nltk.corpus.stopwords.words('english'))
    # stemmer = nltk.stem.snowball.SnowballStemmer('english')

    documents = [tokenize(c) for c in cards]

    dictionary = corpora.Dictionary(documents)
    dictionary.save(DICTIONARY)

    print('Building dictionary containing %i items' % len(dictionary))

    corpus = [dictionary.doc2bow(doc) for doc in documents]
    corpora.MmCorpus.serialize(CORPUS, corpus)

    tfidf = models.TfidfModel(corpus)
    corpus_tfidf = tfidf[corpus]
    tfidf.save(TFIDF)

    lsi = models.LsiModel(corpus, id2word=dictionary, num_topics=100)
    corpus_lsi = lsi[corpus_tfidf]
    lsi.save(LSI)

    index = similarities.MatrixSimilarity(corpus_lsi)
    index.save(INDEX)
