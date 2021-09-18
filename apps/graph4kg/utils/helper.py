# Copyright (c) 2021 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import math
import time
import os
import csv
import argparse
import json
import numpy as np

from functools import wraps


def uniform(low, high, size, dtype=np.float32):
    """Memory efficient uniform implementation
    """
    rng = np.random.default_rng()
    out = (high - low) * rng.random(size, dtype=dtype) + low
    return out


def timer_wrapper(name):
    """Time counter wrapper
    """

    def decorate(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            print('[{}] start...'.format(name))
            ts = time.time()
            result = func(*args, **kwargs)
            te = time.time()
            print('[{}] finished! It takes {:.4f} sec'.format(name, te - ts))
            return result

        return wrapper

    return decorate


def prepare_save_path(args):
    if not os.path.exists(args.save_path):
        os.mkdir(args.save_path)

    folder = '{}_{}_d_{}_g_{}_{}'.format(args.score, args.dataset,
                                         args.embed_dim, args.gamma, args.tag)
    n = len([x for x in os.listdir(args.save_path) if x.startswith(folder)])
    folder += str(n)
    args.save_path = os.path.join(args.save_path, folder)

    if not os.path.exists(args.save_path):
        os.makedirs(args.save_path)
    else:
        raise IOError('model path %s already exists' % args.save_path)
    return args.save_path


def get_compatible_batch_size(batch_size, neg_sample_size):
    if neg_sample_size < batch_size and batch_size % neg_sample_size != 0:
        old_batch_size = batch_size
        batch_size = int(
            math.ceil(batch_size / neg_sample_size) * neg_sample_size)
        print(
            'batch size ({}) is incompatible to the negative sample size ({}). Change the batch size to {}'.
            format(old_batch_size, neg_sample_size, batch_size))
    return batch_size


def load_model_config(config_f):
    with open(config_f, "r") as f:
        config = json.loads(f.read())
        #config = json.load(f)

    print(config)
    return config


def load_raw_triplet_data(head_f=None,
                          rel_f=None,
                          tail_f=None,
                          emap_f=None,
                          rmap_f=None):
    if emap_f is not None:
        eid_map = {}
        id2e_map = {}
        with open(emap_f, 'r') as f:
            reader = csv.reader(f, delimiter='\t')
            for row in reader:
                eid_map[row[1]] = int(row[0])
                id2e_map[int(row[0])] = row[1]

    if rmap_f is not None:
        rid_map = {}
        id2r_map = {}
        with open(rmap_f, 'r') as f:
            reader = csv.reader(f, delimiter='\t')
            for row in reader:
                rid_map[row[1]] = int(row[0])
                id2r_map[int(row[0])] = row[1]

    if head_f is not None:
        head = []
        with open(head_f, 'r') as f:
            id = f.readline()
            while len(id) > 0:
                head.append(eid_map[id[:-1]])
                id = f.readline()
        head = np.asarray(head)
    else:
        head = None

    if rel_f is not None:
        rel = []
        with open(rel_f, 'r') as f:
            id = f.readline()
            while len(id) > 0:
                rel.append(rid_map[id[:-1]])
                id = f.readline()
        rel = np.asarray(rel)
    else:
        rel = None

    if tail_f is not None:
        tail = []
        with open(tail_f, 'r') as f:
            id = f.readline()
            while len(id) > 0:
                tail.append(eid_map[id[:-1]])
                id = f.readline()
        tail = np.asarray(tail)
    else:
        tail = None

    return head, rel, tail, id2e_map, id2r_map


def load_triplet_data(head_f=None, rel_f=None, tail_f=None):
    if head_f is not None:
        head = []
        with open(head_f, 'r') as f:
            id = f.readline()
            while len(id) > 0:
                head.append(int(id))
                id = f.readline()
        head = np.asarray(head)
    else:
        head = None

    if rel_f is not None:
        rel = []
        with open(rel_f, 'r') as f:
            id = f.readline()
            while len(id) > 0:
                rel.append(int(id))
                id = f.readline()
        rel = np.asarray(rel)
    else:
        rel = None

    if tail_f is not None:
        tail = []
        with open(tail_f, 'r') as f:
            id = f.readline()
            while len(id) > 0:
                tail.append(int(id))
                id = f.readline()
        tail = np.asarray(tail)
    else:
        tail = None

    return head, rel, tail


def load_raw_emb_mapping(map_f):
    assert map_f is not None
    id2e_map = {}
    with open(map_f, 'r') as f:
        reader = csv.reader(f, delimiter='\t')
        for row in reader:
            id2e_map[int(row[0])] = row[1]

    return id2e_map


def load_raw_emb_data(file, map_f=None, e2id_map=None):
    if map_f is not None:
        e2id_map = {}
        id2e_map = {}
        with open(map_f, 'r') as f:
            reader = csv.reader(f, delimiter='\t')
            for row in reader:
                e2id_map[row[1]] = int(row[0])
                id2e_map[int(row[0])] = row[1]
    elif e2id_map is not None:
        id2e_map = []  # dummpy return value
    else:
        assert False, 'There should be an ID mapping file provided'

    ids = []
    with open(file, 'r') as f:
        line = f.readline()
        while len(line) > 0:
            ids.append(e2id_map[line[:-1]])
            line = f.readline()
        ids = np.asarray(ids)

    return ids, id2e_map, e2id_map


def load_entity_data(file=None):
    if file is None:
        return None

    entity = []
    with open(file, 'r') as f:
        id = f.readline()
        while len(id) > 0:
            entity.append(int(id))
            id = f.readline()
    entity = np.asarray(entity)
    return entity


class CommonArgParser(argparse.ArgumentParser):
    def __init__(self):
        super(CommonArgParser, self).__init__()

        self.add_argument(
            '--score', default='TransE', choices=['TransE', 'RotatE', 'OTE'])
        self.add_argument(
            '--data_path',
            type=str,
            default='/home/work/suweiyue/Shared/WikiKG90M/data',
            help='The path of the directory where pgl-ke loads knowledge graph data.'
        )
        self.add_argument(
            '--dataset',
            type=str,
            default='wikikg90m',
            help='The name of the builtin knowledge graph. Currently, it only supports wikikg90m'
        )
        self.add_argument('--format', type=str, default='built_in',
                          help='The format of the dataset. For builtin knowledge graphs,'\
                                  'the foramt should be built_in. For users own knowledge graphs,'\
                                  'it needs to be raw_udd_{htr} or udd_{htr}.')
        self.add_argument('--data_files', type=str, default=None, nargs='+',
                          help='A list of data file names. This is used if users want to train KGE'\
                                  'on their own datasets. If the format is raw_udd_{htr},'\
                                  'users need to provide train_file [valid_file] [test_file].'\
                                  'If the format is udd_{htr}, users need to provide'\
                                  'entity_file relation_file train_file [valid_file] [test_file].'\
                                  'In both cases, valid_file and test_file are optional.')
        self.add_argument(
            '--delimiter',
            type=str,
            default='\t',
            help='Delimiter used in data files. Note all files should use the same delimiter.'
        )
        self.add_argument(
            '--save_path',
            type=str,
            default='ckpts',
            help='the path of the directory where models and logs are saved.')
        self.add_argument(
            '--save_step',
            type=int,
            default=100000,
            help='The step where models and logs are saved.')
        self.add_argument(
            '--no_save_emb',
            action='store_true',
            help='Disable saving the embeddings under save_path.')
        self.add_argument('--num_epoch', type=int, default=1000000,
                          help='The maximal number of steps to train the model.'\
                                  'A step trains the model with a batch of data.')
        self.add_argument(
            '--batch_size',
            type=int,
            default=1000,
            help='The batch size for training.')
        self.add_argument(
            '--test_batch_size',
            type=int,
            default=50,
            help='The batch size used for validation and test.')
        self.add_argument(
            '--num_negs',
            type=int,
            default=1000,
            help='The number of negative samples we use for each positive sample in the training.'
        )
        self.add_argument('--neg_mode', type=str, default='full')
        self.add_argument('--neg_deg_sample', action='store_true',
                          help='Construct negative samples proportional to vertex degree in the training.'\
                                  'When this option is turned on, the number of negative samples per positive edge'\
                                  'will be doubled. Half of the negative samples are generated uniformly while'\
                                  'the other half are generated proportional to vertex degree.')
        self.add_argument(
            '--neg_deg_sample_eval',
            action='store_true',
            help='Construct negative samples proportional to vertex degree in the evaluation.'
        )
        self.add_argument(
            '--neg_sample_size_eval',
            type=int,
            default=1000,
            help='The number of negative samples we use to evaluate a positive sample.'
        )
        self.add_argument(
            '--save_threshold',
            type=float,
            default=0.85,
            help='save threshold for mrr.')
        self.add_argument(
            '--eval_percent',
            type=float,
            default=0.1,
            help='Randomly sample some percentage of edges for evaluation.')
        self.add_argument(
            '--test_percent',
            type=float,
            default=1.0,
            help='Randomly sample some percentage of edges for test.')
        self.add_argument(
            '--no_eval_filter',
            action='store_true',
            help='Disable filter positive edges from randomly constructed negative edges for evaluation'
        )
        self.add_argument(
            '-log',
            '--log_interval',
            type=int,
            default=1000,
            help='Print runtime of different components every x steps.')
        self.add_argument('--eval_interval', type=int, default=50000,
                          help='Print evaluation results on the validation dataset every x steps'\
                                  'if validation is turned on')
        self.add_argument(
            '--test',
            action='store_true',
            help='Evaluate the model on the test set after the model is trained.'
        )
        self.add_argument('--num_workers', type=int, default=4)
        self.add_argument('--ent_times', type=int, default=1)
        self.add_argument('--rel_times', type=int, default=1)
        self.add_argument('--num_proc', type=int, default=1,
                          help='The number of processes to train the model in parallel.'\
                                  'In multi-GPU training, the number of processes by default is set to match the number of GPUs.'\
                                  'If set explicitly, the number of processes needs to be divisible by the number of GPUs.')
        self.add_argument('--num_thread', type=int, default=1,
                          help='The number of CPU threads to train the model in each process.'\
                                  'This argument is used for multiprocessing training.')
        self.add_argument('--force_sync_interval', type=int, default=-1,
                          help='We force a synchronization between processes every x steps for'\
                                  'multiprocessing training. This potentially stablizes the training process'
                                  'to get a better performance. For multiprocessing training, it is set to 1000 by default.')
        self.add_argument(
            '--embed_dim',
            type=int,
            default=200,
            help='The embedding size of relation and entity')
        self.add_argument(
            '--lr',
            type=float,
            default=0.01,
            help='The learning rate. pgl-ke uses Adagrad to optimize the model parameters.'
        )
        self.add_argument(
            '-g',
            '--gamma',
            type=float,
            default=12.0,
            help='The margin value in the score function. It is used by TransX and RotatE.'
        )
        self.add_argument(
            '-de',
            '--double_ent',
            action='store_true',
            help='Double entitiy dim for complex number or canonical polyadic. It is used by RotatE and SimplE.'
        )
        self.add_argument(
            '-dr',
            '--double_rel',
            action='store_true',
            help='Double relation dim for complex number or canonical polyadic. It is used by RotatE and SimplE'
        )
        self.add_argument('-adv', '--neg_adversarial_sampling', action='store_true',
                          help='Indicate whether to use negative adversarial sampling.'\
                                  'It will weight negative samples with higher scores more.')
        self.add_argument(
            '-a',
            '--adversarial_temperature',
            default=1.0,
            type=float,
            help='The temperature used for negative adversarial sampling.')
        self.add_argument(
            '-rc',
            '--reg_coef',
            type=float,
            default=0.000002,
            help='The coefficient for regularization.')
        self.add_argument(
            '-rn',
            '--reg_norm',
            type=int,
            default=3,
            help='norm used in regularization.')
        self.add_argument(
            '-pw',
            '--pairwise',
            action='store_true',
            help='Indicate whether to use pairwise loss function. '
            'It compares the scores of a positive triple and a negative triple')
        self.add_argument(
            '--loss_type',
            default='Logsigmoid',
            choices=['Hinge', 'Logistic', 'Logsigmoid', 'BCE'],
            help='The loss function used to train KGEM.')
        self.add_argument(
            '-m',
            '--margin',
            type=float,
            default=1.0,
            help='hyper-parameter for hinge loss.')
        self.add_argument('--scale_type', type=int, default=0)
        self.add_argument('--ote_size', type=int, default=1)
        self.add_argument('--train_percent', type=float, default=1.0)
        self.add_argument('--lr_decay_rate', type=float, default=None, help='')
        self.add_argument(
            '--lr_decay_interval', type=int, default=10000, help='')
        self.add_argument(
            '--cpu_emb', action='store_true', help='Whether use cpu embedding')
        self.add_argument(
            '--use_feature',
            action='store_true',
            help='Whether use RoBERTa embedding')

        self.add_argument(
            '--filter_mode',
            action='store_true',
            help='Whether filter out true triplets')

        # numpy embedding mmap_mode
        self.add_argument(
            '--tag', type=str, default=0, help='Distinguish save path')

        self.add_argument(
            '--gpu',
            type=int,
            default=[-1],
            nargs='+',
            help='A list of gpu ids, e.g. 0 1 2 4')
        self.add_argument('--mix_cpu_gpu', action='store_true',
                          help='Training a knowledge graph embedding model with both CPUs and GPUs.'\
                                  'The embeddings are stored in CPU memory and the training is performed in GPUs.'\
                                  'This is usually used for training a large knowledge graph embeddings.')
        self.add_argument(
            '--valid',
            action='store_true',
            help='Evaluate the model on the validation set in the training.')
        self.add_argument(
            '--rel_part',
            action='store_true',
            help='Enable relation partitioning for multi-GPU training.')
        self.add_argument('--async_update', action='store_true',
                          help='Allow asynchronous update on node embedding for multi-GPU training.'\
                                  'This overlaps CPU and GPU computation to speed up.')
        self.add_argument('--has_edge_importance', action='store_true',
                          help='Allow providing edge importance score for each edge during training.'\
                                  'The positive score will be adjusted '\
                                  'as pos_score = pos_score * edge_importance')

        self.add_argument('--print_on_screen', action='store_true')
        self.add_argument(
            '--mlp_lr',
            type=float,
            default=0.0001,
            help='The learning rate of optimizing mlp')
        self.add_argument('--seed', type=int, default=0, help='random seed')
