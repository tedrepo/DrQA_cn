#!/usr/bin/env python3

# modified chinese tokenizer, use core_nlp
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
"""Simple wrapper around the Stanford CoreNLP pipeline.

Serves commands to a java subprocess running the jar. Requires java 8.
"""


import copy
import json
import pexpect

from .tokenizer import Tokens, Tokenizer
from . import DEFAULTS
from .zh_features import trans, normalize


class ZhTokenizer(Tokenizer):

    def __init__(self, **kwargs):
        """
        Args:
            annotators: set that can include pos, lemma, and ner.
            classpath: Path to the corenlp directory of jars
            mem: Java heap memory
        """
        # doesn't seem to work ...
        self.classpath = (kwargs.get('classpath') or
                          DEFAULTS['corenlp_classpath'])

        # fixme : specific a path by yourself
        # self.classpath = '/home/amose/corenlp/*'  # fixme : preset classPath
        self.annotators = copy.deepcopy(kwargs.get('annotators', set()))
        self.mem = kwargs.get('mem', '2g')
        self._launch()
        self.trans = trans('drqa/features/zh_dict.json')

    def _launch(self):
        """Start the CoreNLP jar with pexpect."""
        annotators = ['tokenize', 'ssplit']
        if 'ner' in self.annotators:
            annotators.extend(['pos', 'lemma', 'ner'])
        elif 'lemma' in self.annotators:
            annotators.extend(['pos', 'lemma'])
        elif 'pos' in self.annotators:
            annotators.extend(['pos'])
        annotators = ','.join(annotators)
        options = ','.join(['untokenizable=noneDelete',
                            'invertible=true'])
        cmd = ['java', '-mx' + self.mem, '-cp', '\'%s\'' % self.classpath,
               'edu.stanford.nlp.pipeline.StanfordCoreNLP', '-props',
               'StanfordCoreNLP-chinese.properties',
               '-annotators', annotators, '-tokenize.options', options,
               '-outputFormat', 'json', '-prettyPrint', 'false']
        # print(cmd)
        # We use pexpect to keep the subprocess alive and feed it commands.
        # Because we don't want to get hit by the max terminal buffer size,
        # we turn off canonical input processing to have unlimited bytes.
        self.corenlp = pexpect.spawn('/bin/bash', maxread=100000, timeout=60)
        self.corenlp.setecho(False)
        self.corenlp.sendline('stty -icanon')
        self.corenlp.sendline(' '.join(cmd))
        # print(' '.join(cmd))
        self.corenlp.delaybeforesend = 0
        self.corenlp.delayafterread = 0
        self.corenlp.expect_exact('NLP>', searchwindowsize=100)
        print('[init tokenizer done]')

    @staticmethod
    def _convert(token):
        if token == '-LRB-':
            return '('
        if token == '-RRB-':
            return ')'
        if token == '-LSB-':
            return '['
        if token == '-RSB-':
            return ']'
        if token == '-LCB-':
            return '{'
        if token == '-RCB-':
            return '}'
        return token

    def tokenize(self, text):
        # Since we're feeding text to the commandline, we're waiting on seeing
        # the NLP> prompt. Hacky!
        if 'NLP>' in text:
            raise RuntimeError('Bad token (NLP>) in text!')

        # Sending q will cause the process to quit -- manually override
        if text.lower().strip() == 'q':
            token = text.strip()
            index = text.index(token)
            data = [(token, text[index:], (index, index + 1), 'NN', 'q', 'O')]
            return Tokens(data, self.annotators)

        # Minor cleanup before tokenizing.
        clean_text = normalize(text)

        self.corenlp.sendline(clean_text.encode('utf-8'))
        self.corenlp.expect_exact('NLP>', searchwindowsize=100)

        # Skip to start of output (may have been stderr logging messages)
        output = self.corenlp.before
        start = output.find(b'{"sentences":')
        output = json.loads(output[start:].decode('utf-8'))

        data = []
        tokens = [t for s in output['sentences'] for t in s['tokens']]
        for i in range(len(tokens)):
            # Get whitespace
            start_ws = tokens[i]['characterOffsetBegin']
            if i + 1 < len(tokens):
                end_ws = tokens[i + 1]['characterOffsetBegin']
            else:
                end_ws = tokens[i]['characterOffsetEnd']

            data.append((
                self._convert(tokens[i]['word']),
                text[start_ws: end_ws],
                (tokens[i]['characterOffsetBegin'],
                 tokens[i]['characterOffsetEnd']),
                tokens[i].get('pos', None),
                # lemma : translation or pinyin
                self.trans.translate(tokens[i].get('lemma', None),
                                     tokens[i].get('pos', None)),
                # tokens[i].get('lemma', None),
                tokens[i].get('ner', None),
                # self.trans.pinyin(text[start_ws: end_ws])
            ))
            # print(data)
        return Tokens(data, self.annotators)
