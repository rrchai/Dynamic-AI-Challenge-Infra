#!/usr/bin/env python3

import argparse
import json
import os
import tarfile
import numpy as np
from typing import Tuple, List
import synapseclient


def get_args():
    """Set up command-line interface and get arguments without any flags."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-e', '--evaluation_id', type=str,
                        help='The evaluation ID of submission')
    parser.add_argument('-g', '--groundtruth_path', type=str,
                        help='The path to the groundtruth path')
    parser.add_argument('-i', '--input_file', type=str,
                        help='The path to the predictions file')
    parser.add_argument('-o', '--output', type=str, required=False,
                        default='results.json', help='The path to output file')

    return parser.parse_args()


# Since it's a data-to-model challenge, users will take care of taring their predictions locally
def tar(directory, tar_filename) -> None:
    """Tar all files in a directory without including the directory
    Args:
        directory: Directory path to files to tar
        tar_filename:  tar file path
    """
    with tarfile.open(tar_filename, 'w') as tar_f:
        original_dir = os.getcwd()
        os.chdir(directory)
        for file in os.listdir('.'):
            tar_f.add(file, arcname=file)
        os.chdir(original_dir)


def untar(directory: str, tar_filename: str, pattern=None) -> None:
    """Untar a tar file into a directory

    Args:
        directory: Path to directory to untar files
        tar_filename:  tar file path
    """
    with tarfile.open(tar_filename, 'r') as tar_f:
        if pattern:
            for member in tar_f.getmembers():
                if member.isfile() and member.name.endswith(pattern):
                    member.name = os.path.basename(member.name)
                    tar_f.extract(member, path=directory)
        else:
            tar_f.extractall(path=directory)


def ODE_forecast(truth: np.ndarray, prediction: np.ndarray, k: int, modes: int) -> Tuple[float, float]:
    '''Produce long-time and short-time error scores.'''
    [m, n] = truth.shape
    Est = np.linalg.norm(truth[:, 0:k]-prediction[:, 0:k],
                         2)/np.linalg.norm(truth[:, 0:k], 2)

    yt = truth[-modes:, :]
    M = np.arange(-20, 21, 1)
    M2 = np.arange(0, 51, 1)
    yhistxt, xhistx = np.histogram(yt[0, :], bins=M)
    yhistyt, xhisty = np.histogram(yt[1, :], bins=M)
    yhistzt, xhistz = np.histogram(yt[2, :], bins=M2)

    yp = prediction[-modes:, :]
    yhistxp, xhistx = np.histogram(yp[0, :], bins=M)
    yhistyp, xhisty = np.histogram(yp[1, :], bins=M)
    yhistzp, xhistz = np.histogram(yp[2, :], bins=M2)

    norm_yhistxt = np.linalg.norm(yhistxt, 2)
    Eltx = np.linalg.norm(yhistxt-yhistxp, 2) / \
        norm_yhistxt if norm_yhistxt > 0 else 0
    norm_yhistyt = np.linalg.norm(yhistyt, 2)
    Elty = np.linalg.norm(yhistyt-yhistyp, 2) / \
        norm_yhistyt if norm_yhistyt > 0 else 0
    norm_yhistzt = np.linalg.norm(yhistzt, 2)
    Eltz = np.linalg.norm(yhistzt-yhistzp, 2) / \
        norm_yhistzt if norm_yhistzt > 0 else 0

    Elt = (Eltx+Elty+Eltz)/3

    E1 = 100*(1-Est)
    E2 = 100*(1-Elt)

    return E1, E2


def PDE_forecast(truth: np.ndarray, prediction: np.ndarray, k: int, modes: int) -> Tuple[float, float]:
    '''produce long-time and short-time error scores.'''
    [m, n] = truth.shape
    Est = np.linalg.norm(truth[:, 0:k]-prediction[:, 0:k],
                         2)/np.linalg.norm(truth[:, 0:k], 2)

    m2 = 2*modes+1
    Pt = np.empty((m2, 0))
    Pp = np.empty((m2, 0))

    # LONG TIME:  Compute least-square fit to power spectra
    for j in range(1, k+1):
        P_truth = np.multiply(
            np.abs(np.fft.fft(truth[:, n-j])), np.abs(np.fft.fft(truth[:, n-j])))
        P_prediction = np.multiply(
            np.abs(np.fft.fft(prediction[:, n-j])), np.abs(np.fft.fft(prediction[:, n-j])))
        Pt3 = np.fft.fftshift(P_truth)
        Pp3 = np.fft.fftshift(P_prediction)
        Ptnew = Pt3[int(m/2)-modes:int(m/2)+modes+1]
        Ppnew = Pp3[int(m/2)-modes:int(m/2)+modes+1]  # Fixed the variable name

        Pt = np.column_stack((Pt, np.log(Ptnew)))
        Pp = np.column_stack((Pp, np.log(Ppnew)))

    Elt = np.linalg.norm(Pt-Pp, 2)/np.linalg.norm(Pt, 2)

    E1 = 100*(1-Est)
    E2 = 100*(1-Elt)

    return E1, E2


def PDE_forecast_2D(truth: np.ndarray, prediction: np.ndarray, k: int, modes: int, nf: int) -> Tuple[float, float]:
    '''produce long-time and short-time error scores.'''
    [m, n] = truth.shape
    Est = np.linalg.norm(truth[:, 0:k]-prediction[:, 0:k],
                         2)/np.linalg.norm(truth[:, 0:k], 2)

    m2 = 2*modes+1
    Pt = np.empty((m2, 0))
    Pp = np.empty((m2, 0))

    # LONG TIME:  Compute least-square fit to power spectra
    for j in range(1, k+1):
        truth_fft = np.abs(np.fft.fft2(
            truth[:, n-j].reshape((nf, nf), order='F')))
        prediction_fft = np.abs(np.fft.fft2(
            prediction[:, n-j].reshape((nf, nf), order='F')))
        P_truth = np.multiply(truth_fft, truth_fft)
        P_prediction = np.multiply(prediction_fft, prediction_fft)
#        P_truth = np.multiply(np.abs(np.fft.fft(truth[:, n-j])), np.abs(np.fft.fft(truth[:, n-j])))
#        P_prediction = np.multiply(np.abs(np.fft.fft(prediction[:, n-j])), np.abs(np.fft.fft(prediction[:, n-j])))
        Pt3 = np.fft.fftshift(P_truth[:, int(nf/2)+1])
        Pp3 = np.fft.fftshift(P_prediction[:, int(nf/2)+1])

        Ptnew = Pt3[int(nf/2)-modes:int(nf/2)+modes+1]
        # Fixed the variable name
        Ppnew = Pp3[int(nf/2)-modes:int(nf/2)+modes+1]
        # print(Ptnew.shape)

        Pt = np.column_stack((Pt, np.log(Ptnew)))
        Pp = np.column_stack((Pp, np.log(Ppnew)))

    Elt = np.linalg.norm(Pt-Pp, 2)/np.linalg.norm(Pt, 2)
    E1 = 100*(1-Est)
    E2 = 100*(1-Elt)

    return E1, E2


def forecast(truth: np.ndarray, prediction: np.ndarray, system: str) -> List[float]:
    system_to_forecast = {
        'doublependulum': {'function': ODE_forecast, 'params': {'k': 20, 'modes': 1000}},
        'Lorenz': {'function': ODE_forecast, 'params': {'k': 20, 'modes': 1000}},
        'Rossler': {'function': ODE_forecast, 'params': {'k': 20, 'modes': 1000}},
        'KS': {'function': PDE_forecast, 'params': {'k': 20, 'modes': 100}},
        'Lorenz96': {'function': PDE_forecast, 'params': {'k': 20, 'modes': 30}},
        'Kolmogorov': {'function': PDE_forecast_2D, 'params': {'k': 20, 'modes': 30, 'nf': 128}}
    }
    if system in system_to_forecast:
        forecast_func = system_to_forecast[system]['function']
        forecast_params = system_to_forecast[system]['params']
        scores = forecast_func(truth, prediction, **forecast_params)
        return list(scores)
    else:
        return []


def reconstruction(truth: np.ndarray, prediction: np.ndarray) -> float:
    '''Produce reconstruction fit score.'''
    [m, n] = truth.shape
    Est = np.linalg.norm(truth-prediction, 2)/np.linalg.norm(truth, 2)

    E1 = 100*(1-Est)

    return E1


def calculate_all_scores(groundtruth_path: str, predictions_path: str, evaluation_id: str) -> dict:
    '''Calculate scores across all testing datasets.'''
    score_result = {}
    task_mapping = {
        '9615379': [  # Task1
            ('X1', 'forecast', ['stf_E1', 'ltf_E2'], [0, 1])
        ],
        '9615532': [  # Task2
            ('X2', 'reconstruction', ['recon_E3'], [0]),
            ('X3', 'forecast', ['ltf_E4'], [1]),
            ('X4', 'reconstruction', ['recon_E5'], [0]),
            ('X5', 'forecast', ['ltf_E6'], [1])
        ],
        '9615534': [  # Task3
            ('X6', 'forecast', ['stf_E7', 'ltf_E8'], [0, 1])
        ],
        '9615535': [  # Task4
            ('X7', 'forecast', ['stf_E9', 'ltf_E10'], [0, 1]),
            ('X8', 'reconstruction', ['recon_E11'], [0]),
            ('X9', 'reconstruction', ['recon_E12'], [0])
        ]
    }

    # get mapping of inputs and outs for specific task
    task_info = task_mapping.get(evaluation_id)

    # get unique systems
    pred_files = os.listdir(predictions_path)
    pred_systems = list(set(f.split('_')[0] for f in pred_files))
    true_systems = ['doublependulum', 'Lorenz',
                    'Rossler', 'Lorenz96', 'KS', 'Kolmogorov']
    unique_systems = list(set(true_systems) & set(pred_systems))

    for system in unique_systems:
        for prefix, score_metric, score_keys, score_indices in task_info:

            truth_path = os.path.join(
                groundtruth_path, f'Test_{system}/{prefix}test.npy')
            pred_path = os.path.join(
                predictions_path, f'{system}_{prefix}prediction.npy')

            # score provided required files
            if os.path.exists(pred_path) and os.path.exists(truth_path):
                truth = np.load(truth_path)
                pred = np.load(pred_path)

                if score_metric == 'forecast':
                    scores = forecast(truth, pred, system)
                else:
                    scores = (reconstruction(truth, pred),)

                for key, index in zip(score_keys, score_indices):
                    # set the score to 0 if negative
                    score_result[f'{system}_{key}'] = max(scores[index], 0)

    return score_result


def score_submission(groundtruth_path: str, predictions_path: str, evaluation_id: str) -> dict:
    '''Determine the score of a submission.

    Args:
        groundtruth_path (str): path to the groundtruth
        predictions_path (str): path to the predictions file
    Returns:
        result (dict): dictionary containing score, status and errors
    '''
    try:
        # assume predictions are compressed into a tarball file
        # untar the predictions into 'predictions' folder
        untar('predictions', tar_filename=predictions_path, pattern='.npy')
        # score the predictions
        scores = calculate_all_scores(
            groundtruth_path, 'predictions', evaluation_id)

        if scores:
            score_status = 'SCORED'
            message = ''
        else:
            message = f'Score calculation failed; necessary files for the submitted task may be missing.'
            scores = None
            score_status = 'INVALID'
    except Exception as e:
        message = f'Error {e} occurred while scoring'
        scores = None
        score_status = 'INVALID'

    result = {
        'score_status': score_status,
        'score_errors': message,
    }

    if scores:
        result.update(scores)

    return score_status, result


# def get_eval_id(syn: synapseclient.Synapse, submission_id: str) -> str:
#     '''Get evaluation id for the submission
#     Args:
#         syn: Synapse connection
#         submission_id (str): the id of submission
#     Returns:
#         sub_id (str): the evaluation ID, or None if an error occurs.
#     '''
#     try:
#         eval_id = syn.getSubmission(submission_id).get('evaluationId')
#         return eval_id
#     except Exception as e:
#         print(
#             f'An error occurred while retrieving the evaluation ID for submission {submission_id}: {e}')
#         return None


def update_json(results_path: str, result: dict) -> None:
    '''Update the results.json file with the current score and status

    Args:
        results_path (str): path to the results.json file
        result (dict): dictionary containing score, status and errors
    '''
    file_size = os.path.getsize(results_path)
    with open(results_path, 'r') as o:
        data = json.load(o) if file_size else {}
    data.update(result)
    with open(results_path, 'w') as o:
        o.write(json.dumps(data))


if __name__ == '__main__':
    args = get_args()
    eval_id = args.evaluation_id
    groundtruth_path = args.groundtruth_path
    predictions_path = args.input_file
    results_path = args.output

    # extract groundtruth files
    untar('groundtruths', tar_filename=groundtruth_path)
    groundtruth_path = "groundtruths"

    # get scores of submission
    score_status, result = score_submission(
        groundtruth_path, predictions_path, eval_id)

    # update the scores and status for the submsision
    with open(results_path, 'w') as file:
        update_json(results_path, result)
    print(score_status)
