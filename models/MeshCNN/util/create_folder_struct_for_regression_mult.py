import pickle
import os
import pandas as pd
from shutil import copyfile

__author__ = "Andy Wang"
__license__ = "MIT"

source_dir_names =["all_brains_merged_10k"
                   ]

# Load indices
with open("names_04152020_noCrashSubs.pk", "rb") as f:
    indices = pickle.load(f)

# Load metadata
meta = pd.read_csv("meta_data.tsv", delimiter='\t')

# Put participant_id and session_id together to get a unique key and use as index
meta['unique_key'] = meta['participant_id'] + "_" + meta['session_id'].astype(str)
meta.set_index('unique_key', inplace=True)

# This will merge train and val
train_indices = indices["Train"]
val_indices = indices["Val"]
test_indices = indices["Test"]


for source_dir_name in source_dir_names:
    # Where them brains at
    source_dir = rf"datasets/{source_dir_name}"
    # Where them brains should be at
    target_dir = rf"datasets/brains_reg_{source_dir_name[11:]}_aug"

    #### This is for MeshCNN specifically
    if not os.access(target_dir, mode=os.F_OK):
        os.makedirs(f"{target_dir}/Male/train")
        os.makedirs(f"{target_dir}/Male/test")
        os.makedirs(f"{target_dir}/Male/val")
        os.makedirs(f"{target_dir}/Female/train")
        os.makedirs(f"{target_dir}/Female/test")
        os.makedirs(f"{target_dir}/Female/val")
    ####

    file_counter = 0

    for patient in train_indices:
        file_name = f"{patient}.obj"
        gender = meta.loc[patient]['gender']
        source_path = f"{source_dir}/{file_name}"
        dest_path = f"{target_dir}/{gender}/train/{file_name}"
        print("Attempting copy source", source_path)
        print("Attempting copy dest", dest_path)
        copyfile(source_path, dest_path)
        file_counter += 1
        print(f"Copy success, file {file_counter}")

    for patient in val_indices:
        file_name = f"{patient}.obj"
        gender = meta.loc[patient]['gender']
        source_path = f"{source_dir}/{file_name}"
        dest_path = f"{target_dir}/{gender}/val/{file_name}"
        print("Attempting copy source", source_path)
        print("Attempting copy dest", dest_path)
        copyfile(source_path, dest_path)
        file_counter += 1
        print(f"Copy success, file {file_counter}")

    for patient in test_indices:
        file_name = f"{patient}.obj"
        gender = meta.loc[patient]['gender']
        source_path = f"{source_dir}/{file_name}"
        dest_path = f"{target_dir}/{gender}/test/{file_name}"
        print("Attempting copy source", source_path)
        print("Attempting copy dest", dest_path)
        copyfile(source_path, dest_path)
        file_counter += 1
        print(f"Copy success, file {file_counter}")
