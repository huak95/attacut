import numpy as np
import torch

from torch.utils.data import Dataset

from attacut import utils, preprocessing, logger

log = logger.get_logger(__name__)

class SequenceDataset(Dataset):
    def __init__(self, path: str=None):
        if path:
            self.load_preprocessed_data(path)

    def __len__(self):
        return self.total_samples

    def __getitem__(self, index):
        return self.data[index]

    def load_preprocessed_data(self, path):
        self.data = []

        suffix = path.split("/")[-1]
        with open(path) as f, \
            utils.Timer("load-seq-data--%s" % suffix) as timer:
            for line in f:
                self.data.append(SequenceDataset._process_line(line))

        self.total_samples = len(self.data)

    @staticmethod
    def prepare_model_inputs(inputs, device="cpu"):

        x, seq_lengths = inputs[0]
        x = x.to(device)
        y = inputs[1].float().to(device).reshape(-1)

        return (x, seq_lengths), y, y.shape[0]


    def make_feature(self, txt):
        raise NotImplementedError

    def setup_featurizer(self, path: str):
        raise NotImplementedError

    @staticmethod
    def _process_line(line):
        # only use when training
        raise NotImplementedError

    @staticmethod
    def collate_fn(batch):
        # only use when training
        raise NotImplementedError

class CharacterSeqDataset(SequenceDataset):
    def setup_featurizer(self, path: str):
        self.dict = utils.load_dict(f"{path}/characters.json")

        return dict(num_tokens=len(self.dict))

    def make_feature(self, txt):
        characters = list(txt)
        ch_ix = list(map(lambda c: preprocessing.mapping_char(self.dict, c), characters))

        features = np.array(ch_ix, dtype=np.int64).reshape((1, -1))

        seq_lengths = np.array([features.shape[-1]], dtype=np.int64)

        return characters, (torch.from_numpy(features), torch.from_numpy(seq_lengths))

    @staticmethod
    def _process_line(line):
        label, indices = line.split("::")

        y = np.array(list(label)).astype(int)
        x = np.array(indices.split(" ")).astype(int)

        seq = len(y)

        return (x, seq), y

    @staticmethod
    def collate_fn(batch):
        total_samples = len(batch)

        seq_lengths = np.array(list(map(lambda x: x[0][1], batch)))
        max_length = np.max(seq_lengths)

        features = np.zeros((total_samples, max_length), dtype=np.int64)
        labels = np.zeros((total_samples, max_length), dtype=np.int64)

        for i, s in enumerate(batch):
            b_feature = s[0][0]
            total_features = len(b_feature)
            features[i, :total_features] = b_feature
            labels[i, :total_features] = s[1]

        seq_lengths = torch.from_numpy(seq_lengths)
        seq_lengths, perm_idx = seq_lengths.sort(0, descending=True)


        inputs = (torch.from_numpy(features)[perm_idx], seq_lengths)

        labels = torch.from_numpy(labels)[perm_idx]

        return inputs, labels


class SyllableCharacterSeqDataset(SequenceDataset):
    def setup_featurizer(self, path: str):
        self.ch_dict = utils.load_dict(f"{path}/characters.json")
        self.sy_dict = utils.load_dict(f"{path}/syllables.json")

        return dict(
            num_char_tokens=len(self.ch_dict),
            num_tokens=len(self.sy_dict)
        )
    
    def make_feature(self, txt):
        syllables = preprocessing.syllable_tokenize(txt)

        sy2idx, ch2idx = self.sy_dict, self.ch_dict

        ch_ix, syllable_ix = [], []

        for s in syllables:
            s_mapped = preprocessing.map_syllable_token(s)
            six = sy2idx.get(s, sy2idx['<UNK>'])

            chs = list(map(lambda c: preprocessing.mapping_char(ch2idx, c), list(s)))

            ch_ix.extend(chs)
            syllable_ix.extend([six]*len(chs))

        features = np.stack((ch_ix, syllable_ix), axis=0) \
            .reshape((1, 2, -1)) \
            .astype(np.int64)

        seq_lengths = np.array([features.shape[-1]], dtype=np.int64)

        return list(txt), (torch.from_numpy(features), torch.from_numpy(seq_lengths))

    # def __getitem__(self, index):
    #     label, character_indices, syllable_indices = self.data[index]
    #     y = np.array(list(label)).astype(int)

    #     cx = np.array(character_indices.split(" ")).astype(int)
    #     sx = np.array(syllable_indices.split(" ")).astype(int)

    #     seq = len(y)

    #     x = np.stack((cx, sx), axis=0)

    #     return (x, seq), y

    @staticmethod
    def collate_fn(batch):
        total_samples = len(batch)

        seq_lengths = np.array(list(map(lambda x: x[0][1], batch)))
        max_length = np.max(seq_lengths)

        features = np.zeros((total_samples, 2, max_length), dtype=np.int64)
        labels = np.zeros((total_samples, max_length), dtype=np.int64)

        for i, s in enumerate(batch):
            b_feature = s[0][0]
            total_features = b_feature.shape[1]
            features[i, :, :total_features] = b_feature
            labels[i, :total_features] = s[1]

        seq_lengths = torch.from_numpy(seq_lengths)
        seq_lengths, perm_idx = seq_lengths.sort(0, descending=True)

        inputs = (torch.from_numpy(features)[perm_idx], seq_lengths)

        labels = torch.from_numpy(labels)[perm_idx]

        return inputs, labels
