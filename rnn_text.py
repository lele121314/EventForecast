import os
import pickle
import sys
import getopt

import numpy as np
from keras.models import Sequential
from keras.layers import Flatten, Dropout, Dense 
from keras.layers.convolutional import Conv1D
from keras.layers.convolutional import MaxPooling1D
from keras.layers.embeddings import Embedding
from keras.layers.recurrent import LSTM
import keras.optimizers as opt
#import gensim

global LEN  # the input length
global DIM  # dimension of word vector
global BATCH

# index and embed raw text
def gen_embed_model(modelFile):
    vocab = {}  # {'word': index, ...}
    with open(modelFile, 'r') as f:
        line = f.readline()
        [length, dim] = line.split(' ')
        vec = np.zeros((int(length)+1, int(dim)), dtype = np.float64)    # {index: [vector], ...}
        line = f.readline()
        i = 1
        while line != '':
            index = line.find(' ')
            word = line[:index]
            vector = []
            for e in line[index+1:].split(' '):
                try:
                    vector.append(float(e))
                except Exception:
                    print('float' + e)
            vocab[word] = i
            vec[i] = np.array(vector, dtype=np.float64)
            line = f.readline()
            i = i+1
    return vocab, vec

# extract data from one line of text, require strip(' ') first
# return np arrays
def extract_data(line, model, weights=None):
    content = line.split('\t')
    result = compute_result(content[:-1])
    source = content[-1]
    data = []
    #print(weights is None)
    for word in source.split(' '):
        try:
            if weights is None:
                data.append(model[word])    # convert word to index
            else:
                data.append(weights[model[word]])   # convert to vector
        except:
            pass
            #data.append(model['unk'])
    # make every input have same length
    if weights is None:
        data = padding(data, False)
    else:
        data = padding(data, True)
    return np.array(data, dtype=np.float64), np.array(result, dtype=np.float64)

# compute results based on the attributes
def compute_result(attrs):
    # attrs: isroot, quadclass, glodstein, mentions, sources, articles, tone
    return round((float(attrs[3]) + float(attrs[5]))/2, 2)

# padding zeros
def padding(data, useVec):
    global LEN
    global DIM
    length = len(data)
    if length < LEN:
        if useVec:
            zero = np.zeros(data[0].shape)  # append zero vectors
        else:
            zero = 0    # append zeros
        for i in range(length,LEN):
            data.append(zero)
    elif length > LEN:
        data = data[:LEN]
    return data

# extract input data and results from a file
def build_dataset(fileName, vocab, weights=None):
    trainData, trainResult = [], []
    with open(fileName, 'r') as src:
        line = src.readline().strip('\n')
        while line != '':
            # extract data and result from each line
            data, result = extract_data(line.strip(' '), vocab, weights=weights)
            trainData.append(data)
            trainResult.append(result)
            line = src.readline().strip('\n')
    return trainData, trainResult

# a generator used to fit the rnn model
def train_data_generator(dataPath, limit, vocab):
    total = 2528
    index = 0
    while True:
        inputs, targets = build_dataset('%s%d'%(dataPath, index), vocab)
        for i in range(1, limit):
            index += 1
            if index == total:
                index = 0
            newInputs, newTargets = build_dataset('%s%d'%(dataPath, index), vocab)
            inputs.extend(newInputs)
            targets.extend(newTargets)
        if index%50 == 0:
            print(index)
        yield (np.array(inputs, dtype=np.int32), np.array(targets, dtype=np.float64))
        index += 1
        if index == total:
            index = 0
def train_data_generator2(dataPath, weights):
    total = 2528
    index = 0
    while True:
        inputs = np.load('%s%d%s'%(dataPath, index, '_x.npy'))
        result = np.load('%s%d%s'%(dataPath, index, '_y.npy'))
        data = np.zeros([BATCH,LEN,DIM],dtype=np.float64)
        for i in range(len(inputs)):
            for j in range(len(inputs[i])):
                data[i][j] = weights[inputs[i][j]]
        if index%50 == 0:
            print(index)
        yield data, result
        index += 1
        if index == total:
            index = 0

# train rnn model. dataPath example: news_50/news_stem_
def model_rnn(vocab, weights, dataPath, batchn, epoch):
    global LEN
    global DIM
    global BATCH
    # build and fit model
    model = Sequential()
    #model.add(Embedding(400001,50, input_length=LEN, mask_zero=True,weights=[embedModel]))
    model.add(LSTM(50, input_shape=(LEN, DIM), activation='relu'))
    model.add(Dropout(0.5))
    model.add(Dense(1))
    sgd = opt.SGD(lr=0.1, decay=1e-2, momentum=0.9)
    model.compile(loss='mean_squared_error', optimizer='adam')
    print(model.summary())
    #model.fit_generator(train_data_generator2('news_50_bin/news_stem_'), 500, epochs=10, verbose=2, validation_data=None)
    index = 0
    while True:
        data, result = build_dataset('%s%d'%(dataPath, index%2528), vocab, weights=weights)
        for i in range(1, batchn):
            index += 1
            newData, newResult = build_dataset('%s%d'%(dataPath, index), vocab, weights=weights)
            data.extend(newData)
            result.extend(newResult)
        model.fit(np.array(data, dtype=np.float64), np.array(result, dtype=np.float64), epochs=8, batch_size=BATCH, verbose=2, validation_split = 0.15)
        model.save('hotnews_r_%d_%d.h5'%(BATCH, index))
        testx, testy = build_dataset('news_50/news_stem_2528', vocab, weights=weights)
        predict = model.predict(np.array(testx, dtype=np.float64))
        for i in range(len(testy)):
            print(testy[i], predict[i])
        index += 1
        if index > epoch:
            return model

# train cnn model
def model_cnn(vocab, weights, dataPath, batchn, epoch):
    global LEN
    global DIM
    global BATCH
    model = Sequential()
    #model.add(Embedding(400001, 50, input_length=LEN, mask_zero=False,weights=[embedModel]))
    model.add(Conv1D(filters=32, kernel_size=30, padding='same', activation='relu'))
    model.add(MaxPooling1D(pool_size=2))
    model.add(Flatten())
    model.add(Dense(250, activation='sigmoid'))
    model.add(Dense(1, activation='sigmoid'))
    model.compile(loss='binary_crossentropy', optimizer='adam', metrics=['accuracy'])
    print(model.summary())
    index = 0
    while True:
        data, result = build_dataset('%s%d'%(dataPath, index%2528), vocab, weights)
        for i in range(1, batchn):
            index += 1
            newData, newResult = build_dataset('%s%d'%(dataPath, index), vocab, weights)
            data.extend(newData)
            result.extend(newResult)
        model.fit(np.array(data, dtype=np.float64), np.array(result, dtype=np.float64), epochs=10, batch_size=BATCH, verbose=2, validation_split = 0.1)
        model.save('hotnews_c_%d_%d.h5'%(BATCH, index))
        testx, testy = build_dataset('news_50/news_stem_2528', vocab, weights=weights)
        predict = model.predict(np.array(testx), dtype=np.float64)
        for i in range(len(testy)):
            print(testy[i], predict[i])
        index += 1
        if index > epoch:
            return model

def main():
    global LEN
    global BATCH
    global DIM
    # default values
    
    vocabFile = 'vocab_glove50.pkl'
    w2vfile = 'weights_glove50.npy'
    dataPath = 'news_50_num/news_stem_'
    batchn = 10
    BATCH = 50*batchn
    epoch = 50
    LEN = 1000
    usemodel = 'r'
    # parse arguments
    options,args = getopt.getopt(sys.argv[1:],"v:w:d:b:l:m:e:")
    for opt, para in options:
        if opt == '-v':
            vocabFile = para
        if opt == '-w':
            w2vfile = para
        if opt == '-d':
            dataPath = para
        if opt == '-b':
            batchn = int(para)
        if opt == '-l':
            LEN = int(para)
        if opt == '-m':
            usemodel = para
        if opt == '-e':
            epochs = int(para)
        
    weights = np.load(w2vfile)  # load weights from file
    DIM = weights.shape[1]
    with open(vocabFile, 'rb') as handle:   # load vocabulary from file
        vocab = pickle.load(handle)
    # train model
    if usemodel == 'r': # use rnn model
        model = model_rnn(vocab, weights, dataPath, batchn, epoch)
    else:   # use cnn model
        model = model_cnn(vocab, weights, dataPath, batchn, epoch)
    
    model.save('hotnews.h5')
    testx, testy = build_dataset('news_50/news_stem_2528', vocab, weights)
    predict = model.predict(np.array(testx, dtype=np.float64))
    for i in range(len(testy)):
        print(testy[i], predict[i])

if __name__ == '__main__':
    main()
'''
global LEN
global BATCH
global DIM
# default values

vocabFile = 'vocab_glove50.pkl'
w2vfile = 'w2v_weights_glove50.npy'
dataPath = 'news_50/news_stem_'
batchn = 10
BATCH = 50*batchn
epoch = 50
LEN = 1000
usemodel = 'r'

weights = np.load(w2vfile)  # load weights from file
DIM = weights.shape[1]
with open(vocabFile, 'rb') as handle:   # load vocabulary from file
    vocab = pickle.load(handle)

testx, testy = build_dataset('news_50/news_stem_2528', vocab, weights)
'''
