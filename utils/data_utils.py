import mne
import numpy as np
from mne.io import read_raw_edf
from mne.datasets import eegbci
import torch
from data.gpt2_dataset import GPT2ActivationDataset
from data.synthetic_dataset import generate_synthetic_data
import wandb
from utils.gpt2_utils import stream_data, process_activations


def load_eeg_data(subjects, runs, interval):
    '''
    Placeholder function that works for a toy dataset
    '''
    data = []
    max_seq_len = 0

    for subject in subjects:
        for run in runs:
            raw = read_raw_edf(eegbci.load_data(subject, run)[0], preload=True)
            raw.filter(7.0, 30.0, fir_design="firwin", skip_by_annotation="edge")
            picks = mne.pick_types(
                raw.info, meg=False, eeg=True, stim=False, eog=False, exclude="bads"
            )
            sfreq = raw.info["sfreq"]
            run_data = np.concatenate(
                [
                    raw.get_data(picks, start=i, stop=i + int(interval * sfreq))
                    for i in range(0, raw.n_times, int(interval * sfreq))
                ],
                axis=1,
            )
            max_seq_len = max(max_seq_len, run_data.shape[1])
            data.append(run_data.T)

    padded_data = []
    for seq in data:
        pad_width = ((0, max_seq_len - seq.shape[0]), (0, 0))
        padded_seq = np.pad(seq, pad_width, mode="constant")
        padded_data.append(padded_seq)

    padded_data = np.array(padded_data)
    return padded_data


def generate_synthetic_dataset(config, device):
    num_features = config.get('num_features', 256)
    num_true_features = config.get('num_ground_features', 512)
    total_data_points = config.get('total_data_points', 100000)
    num_active_features_per_point = config.get('num_active_features_per_point', 42)
    batch_size = config.get('data_batch_size', 1000)

    generated_data, true_features = generate_synthetic_data(
        num_features,
        num_true_features,
        total_data_points,
        num_active_features_per_point,
        batch_size,
        device=device
    )

    train_dataset = torch.utils.data.TensorDataset(generated_data)

    dataset_artifact = wandb.Artifact('synthetic_dataset', type='dataset')

    dataset_path = 'synthetic_dataset.pth'
    torch.save(train_dataset, dataset_path)
    dataset_artifact.add_file(dataset_path)

    true_features_path = 'true_features.pth'
    torch.save(true_features, true_features_path)
    dataset_artifact.add_file(true_features_path)

    wandb.log_artifact(dataset_artifact)


def generate_gpt2_dataset(device):
    activation_dataset = GPT2ActivationDataset(model_name='gpt2', device=device)

    all_data = []
    data_stream = stream_data()
    for entry in data_stream:
        input_text = entry["text"]
        if not input_text.strip():
            continue

        activations, tokens = activation_dataset(input_text)
        processed_activations = process_activations(activations)
        all_data.append((processed_activations, tokens))

    artifact = wandb.Artifact('gpt2_activations_dataset', type='dataset')
    dataset_path = 'gpt2_dataset.pth'
    torch.save(all_data, dataset_path)
    artifact.add_file(dataset_path)
    wandb.log_artifact(artifact)
