# Copyright (c) 2021 PaddlePaddle Authors. All Rights Reserved
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
"""
Score functions of different knowledge graph embedding models.
"""

import numpy as np
import paddle
import paddle.nn as nn
from paddle.nn.functional import log_sigmoid


class ScoreFunc(object):
    """Abstract implementation of score function
    """

    def __init__(self):
        super(ScoreFunc, self).__init__()

    def __call__(self, head, rel, tail):
        raise NotImplementedError(
            'score function from head, relation to tail not implemented')

    def inverse(self, head, rel, tail):
        """Score function from tail, relation to head
        """
        raise NotImplementedError(
            'score function from tail, relation to head not implemented')


class TransEScore(ScoreFunc):
    """
    TransE: Translating embeddings for modeling multi-relational data.
    https://www.utc.fr/~bordesan/dokuwiki/_media/en/transe_nips13.pdf
    """

    def __init__(self, gamma):
        super(TransEScore, self).__init__()
        self.gamma = gamma

    def __call__(self, head, rel, tail):
        # score = tail - (head + rel)
        # return self.gamma - paddle.norm(score, p=2, axis=-1)
        head = head + rel
        return self.gamma - self.cdist(head, tail)

    def inverse(self, head, rel, tail):
        tail = tail - rel
        return self.gamma - self.cdist(tail, head)

    def cdist(self, a, b):
        """Euclidean distance
        """
        a_s = paddle.norm(a, p=2, axis=-1).pow(2)
        b_s = paddle.norm(b, p=2, axis=-1).pow(2)
        dist_score = -2 * paddle.matmul(a, b.transpose([0, 2, 1]))
        dist_score = dist_score + b_s.unsqueeze(-2) + a_s.unsqueeze(-1)
        dist_score = paddle.sqrt(paddle.clip(dist_score, min=1e-30))
        return dist_score

    # def cdist_1(self, a, b):
    #     a_s = a * a
    #     b_s = b * b
    #     dist_score = -2 * paddle.bmm(a, b.transpose(
    #         [0, 2, 1])) + b_s.unsqueeze(-2) + a_s.unsqueeze(-1)
    #     dist_score = paddle.sqrt(paddle.clip(dist_score, min=1e-30))
    #     return dist_score

    # def cdist_2(self, a, b):
    #     c = a.unsqueeze(-1) - b.unsqueeze(-2)
    #     dist_score = paddle.sqrt(c * c + 1e-12)
    #     return dist_score


class RotatEScore(ScoreFunc):
    """
    RotatE: Knowledge Graph Embedding by Relational Rotation in Complex Space.
    https://arxiv.org/abs/1902.10197
    """

    def __init__(self, gamma, emb_init):
        super(RotatEScore, self).__init__()
        self.gamma = gamma
        self.emb_init = emb_init
        self.epsilon = 1e-12

    def __call__(self, head, rel, tail):
        re_head, im_head = paddle.chunk(head, chunks=2, axis=-1)
        re_tail, im_tail = paddle.chunk(tail, chunks=2, axis=-1)
        phase_rel = rel / (self.emb_init / np.pi)
        re_rel, im_rel = paddle.cos(phase_rel), paddle.sin(phase_rel)

        re_score = re_rel * re_head - im_rel * im_tail
        im_score = re_rel * im_head + im_rel * re_head
        re_score = re_score - re_tail
        im_score = im_score - im_tail

        score = paddle.sqrt(re_score * re_score + im_score * im_score +
                            self.epsilon)
        score = self.gamma - paddle.sum(score, axis=-1)
        return score

    def inverse(self, head, rel, tail):
        re_head, im_head = paddle.chunk(head, chunks=2, axis=-1)
        re_tail, im_tail = paddle.chunk(tail, chunks=2, axis=-1)
        phase_rel = rel / (self.emb_init / np.pi)
        re_rel, im_rel = paddle.cos(phase_rel), paddle.sin(phase_rel)

        re_score = re_rel * re_tail + im_rel * im_tail
        im_score = re_rel * im_tail - im_rel * re_tail
        re_score = re_score - re_head
        im_score = im_score - im_head

        score = paddle.sqrt(re_score * re_score + im_score * im_score +
                            self.epsilon)
        score = self.gamma - paddle.sum(score, axis=-1)
        return score


class OTEScore(ScoreFunc):
    """OTE score
    """

    def __init__(self, gamma, num_elem, scale_type=0):
        super(OTEScore, self).__init__()
        self.gamma = gamma
        self.num_elem = num_elem
        self.scale_type = scale_type
        self.use_scale = self.scale_type > 0

    def __call__(self, head, rel, tail):
        rel = self.orth_rel_embedding(rel)
        score = self.score(head, rel, tail)
        return self.gamma - score

    def inverse(self, head, rel, tail):
        rel = self.orth_rel_embedding(rel)
        rel = self.orth_reverse_mat(rel)
        score = self.score(tail, rel, head)
        return self.gamma - score

    def score(self, inputs, inputs_rel, inputs_last):
        inputs_size = inputs.shape
        assert inputs_size[:-1] == inputs_rel.shape[:-1]
        num_dim = inputs_size[-1]
        inputs = inputs.reshape([-1, 1, self.num_elem])
        if self.use_scale:
            rel = inputs_rel.reshape([-1, self.num_elem, self.num_elem + 1])
            scale = self.get_scale(rel[:, :, self.num_elem:])
            scale = scale / scale.norm(axis=-1, p=2, keepdim=True)
            rel_scale = rel[:, :, :self.num_elem] * scale
            outputs = paddle.bmm(inputs, rel_scale)
        else:
            rel = inputs_rel.reshape([-1, self.num_elem, self.num_elem])
            outputs = paddle.bmm(inputs, rel)
        outputs = outputs.reshape(inputs_size)
        outputs = outputs - inputs_last
        outputs_size = outputs.shape
        num_dim = outputs_size[-1]
        outputs = outputs.reshape([-1, self.num_elem])
        scores = outputs.norm(
            p=2, axis=-1).reshape([-1, num_dim // self.num_elem]).sum(
                axis=-1).reshape(outputs_size[:-1])
        return scores

    def neg_score(self, inputs, inputs_rel, inputs_last, neg_sample_size,
                  chunk_size):
        inputs_size = inputs.shape
        assert inputs_size[:-1] == inputs_rel.shape[:-1]
        num_dim = inputs_size[-1]
        inputs = inputs.reshape([-1, 1, self.num_elem])
        if self.use_scale:
            rel = inputs_rel.reshape([-1, self.num_elem, self.num_elem + 1])
            scale = self.get_scale(rel[:, :, self.num_elem:])
            scale = scale / scale.norm(axis=-1, p=2, keepdim=True)
            rel_scale = rel[:, :, :self.num_elem] * scale
            outputs = paddle.bmm(inputs, rel_scale)
        else:
            rel = inputs_rel.reshape([-1, self.num_elem, self.num_elem])
            outputs = paddle.bmm(inputs, rel)
        outputs = outputs.reshape([-1, chunk_size, 1, inputs_size[-1]])
        inputs_last = inputs_last.reshape(
            [-1, 1, neg_sample_size, inputs_size[-1]])
        outputs = outputs - inputs_last
        outputs_size = outputs.shape
        num_dim = outputs_size[-1]
        outputs = outputs.reshape([-1, self.num_elem])
        scores = outputs.norm(
            p=2, axis=-1).reshape([-1, num_dim // self.num_elem]).sum(
                axis=-1).reshape(outputs_size[:-1])
        return scores

    def get_scale(self, scale):
        if self.scale_type == 1:
            return scale.abs()
        if self.scale_type == 2:
            return scale.exp()
        raise ValueError("Scale Type %d is not supported!" % self.scale_type)

    def reverse_scale(self, scale, eps=1e-9):
        if self.scale_type == 1:
            return 1 / (abs(scale) + eps)
        if self.scale_type == 2:
            return -scale
        raise ValueError("Scale Type %d is not supported!" % self.scale_type)

    def scale_init(self):
        if self.scale_type == 1:
            return 1.0
        if self.scale_type == 2:
            return 0.0
        raise ValueError("Scale Type %d is not supported!" % self.scale_type)

    def orth_embedding(self, embeddings, eps=1e-18, do_test=True):
        num_emb = embeddings.shape[0]
        assert embeddings.shape[1] == self.num_elem
        assert embeddings.shape[2] == (self.num_elem +
                                       (1 if self.use_scale else 0))
        if self.use_scale:
            emb_scale = embeddings[:, :, -1]
            embeddings = embeddings[:, :, :self.num_elem]

        u = [embeddings[:, 0]]
        uu = [0] * self.num_elem
        uu[0] = (u[0] * u[0]).sum(axis=-1)
        u_d = embeddings[:, 1:]
        for i in range(1, self.num_elem):
            u_d = u_d - u[-1].unsqueeze(axis=1) * (
                (embeddings[:, i:] * u[i - 1].unsqueeze(axis=1)).sum(
                    axis=-1) / uu[i - 1].unsqueeze(axis=1)).unsqueeze(-1)
            u_i = u_d[:, 0]
            if u_d.shape[1] > 1:
                u_d = u_d[:, 1:]
            uu[i] = (u_i * u_i).sum(axis=-1)
            u.append(u_i)

        u = paddle.stack(u, axis=1)  #num_emb X num_elem X num_elem
        u_norm = u.norm(axis=-1, keepdim=True, p=2)
        u = u / u_norm
        if self.use_scale:
            u = paddle.concat([u, emb_scale.unsqueeze(-1)], axis=-1)
        return u

    def orth_rel_embedding(self, relation_embedding):
        rel_emb_size = relation_embedding.shape
        ote_size = self.num_elem
        scale_dim = 1 if self.use_scale else 0
        rel_embedding = relation_embedding.reshape(
            [-1, ote_size, ote_size + scale_dim])
        rel_embedding = self.orth_embedding(rel_embedding).reshape(
            rel_emb_size)
        return rel_embedding

    def orth_reverse_mat(self, rel_embeddings):
        rel_size = rel_embeddings.shape
        if self.use_scale:
            rel_emb = rel_embeddings.reshape(
                [-1, self.num_elem, self.num_elem + 1])
            rel_mat = rel_emb[:, :, :self.num_elem].transpose([0, 2, 1])
            rel_scale = self.reverse_scale(rel_emb[:, :, self.num_elem:])
            rel_embeddings = paddle.concat(
                [rel_mat, rel_scale], axis=-1).reshape(rel_size)
        else:
            rel_embeddings = rel_embeddings.reshape(
                [-1, self.num_elem, self.num_elem]).transpose(
                    [0, 2, 1]).reshape(rel_size)
        return rel_embeddings

    #     if neg_head:
    #         relations = self.orth_reverse_mat(relations)
    #         score_result = self.score(tails, relations, heads)
    #     else:
    #         score_result = self.score(heads, relations, tails)
    #     score = self.gamma - score_result
    #     return score

    # def get_neg_score(self,
    #                   heads,
    #                   relations,
    #                   tails,
    #                   batch_size,
    #                   mini_batch_size,
    #                   neg_sample_size,
    #                   neg_head=True):
    #     if neg_head:
    #         relations = self.orth_rel_embedding(relations)
    #         relations = self.orth_reverse_mat(relations)
    #         score_result = self.neg_score(tails, relations, heads,
    #                                       neg_sample_size, mini_batch_size)
    #         score = self.gamma - score_result
    #         return score
    #     else:
    #         relations = self.orth_rel_embedding(relations)
    #         score_result = self.neg_score(heads, relations, tails,
    #                                       neg_sample_size, mini_batch_size)
    #         score = self.gamma - score_result
    #         return score
