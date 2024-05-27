## UDTL-based-Intelligent-Diagnosis

## Overview


This repository includes code that applies UDA (Unsupervised Domain Adaptation) methodologies for fault diagnosis of rotating machinery in imbalanced situations.

Please be aware that I have referred to two repositories, which are cited below.

It is planned to be updated step by step.

If you want to specify the imbalance ratio for the training data of the target dataset, add the imbalance_ratio parameter to the Dataset function in `train_utils.py.`

### Domain Adaptation
- **ACDANN** - Integrating expert knowledge with domain adaptation for unsupervised fault diagnosis. [Published in TIM 2021](https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9612159) | [View Code](/models/ACDANN.py)
- **CDAN** - Conditional adversarial domain adaptation. [Published in NIPS 2018](http://papers.nips.cc/paper/7436-conditional-adversarial-domain-adaptation) | [View Code](/models/CDAN.py) 
- **CORAL** - Deep coral: Correlation alignment for deep domain adaptation. [Published in ECCV 2016](https://arxiv.org/abs/1607.01719) | [View Code](/models/CORAL.py)
- **DANN** - Unsupervised domain adaptation by backpropagation. [Published in ICML 2015](http://proceedings.mlr.press/v37/ganin15.pdf) | [View Code](/models/DANN.py)
- **DDTLN** - Deep discriminative transfer learning network for cross-machine fault diagnosis. [Published in Mechanical Systems and Signal Processing 2023](https://www.sciencedirect.com/science/article/pii/S0888327022009529) | [View Code](/models/DDTLN.py)

## Getting Started

### Requirements
- Python 3.6.9
- Numpy 1.19.5
- Pandas 1.1.5
- tqdm 4.62.3
- Scipy 1.2.1
- pytorch >= 1.11.0
- torchvision >= 0.40


### Repository Access
You can access our repository either by direct download or using git clone. Here’s how:
#### Direct Download
1. Click on the 'Code' button and select 'Download ZIP'.
2. Extract the ZIP file to your desired location.
#### Using Git Clone
1. Open your command line interface.
2. Navigate to the directory where you wish to clone the repository.
3. Run the command:

```shell
git clone https://github.com/yongmini/UDA_Bearing_Fault_Diagnosis.git
```

## Accessing Datasets
### Supported datasets
Our repository supports several public datasets for fault diagnosis, with accompanying loading code. These include:
- **[CWRU](https://engineering.case.edu/bearingdatacenter)** - Case Western Reserve University dataset.
- **[JNU Bearing Dataset](http://mad-net.org:8765/explore.html?t=0.5831516555847212.)** -Jiangnan University dataset

### Setting Up Dataset Directory
- Create a folder named "datasets" in the root directory of the cloned repository.
- Download the desired datasets and place them into this "datasets" folder, follow the steps below:

#### Within-dataset Transfer
For analyzing a specific dataset under different working conditions:
1. Divide the dataset into separate folders named "condition_0", "condition_1", etc., each representing a unique operational condition.

Example folder structure for CWRU dataset:
```
.
└── datasets
    └── CWRU
        ├── condition_0
        │   ├── ball_07
        │   │   └── 122.mat
        │   ├── inner_07
        │   │   └── 109.mat
        │   ...
        ├── condition_1
        │   ├── ball_07
        │   │   └── 123.mat
        │   ...
        ├── condition_2
        ...
```

## Training Procedures
### Within-dataset transfer
Train models using data from the same dataset but different operational conditions.

#### One-to-One Transfer
Example: Transfer from CWRU operation condition 0 to condition 1.
```shell
python train.py --model_name DAN --source CWRU_0 --target CWRU_1 --train_mode single_source --cuda_device 0
```
#### imbalanced setting
```shell
python train.py --model_name CNN --source CWRU_0 --target CWRU_1 --train_mode single_source --cuda_device 0 --imba True
```

🛠️ For more experimental settings, please modify the arguments in `opt.py`.

## Contact

We welcome feedback, inquiries, and suggestions to improve our work. If you encounter any issues with our code or have recommendations, please don't hesitate to reach out. feel free to post your queries or suggestions in the [Issues](https://github.com/yongmini/UDA_Bearing_Fault_Diagnosis/issues) section of our GitHub repository.


## Citation
Your support in citing our project when used in your research is highly appreciated. It helps in the recognition and dissemination of our work. Please use the following citation format:
```latex
@misc{TL-Bearing-Fault-Diagnosis,
    author = {Jinyuan Zhang},
    title = {TL-Bearing-Fault-Diagnosis},
    year = {2022},
    publisher = {GitHub},
    journal = {GitHub repository},
    howpublished = {\url{https://github.com/Feaxure-fresh/TL-Bearing-Fault-Diagnosis}}
}

```

```latex
@misc{Zhao2019,
author = {Zhibin Zhao and Qiyang Zhang and Xiaolei Yu and Chuang Sun and Shibin Wang and Ruqiang Yan and Xuefeng Chen},
title = {Unsupervised Deep Transfer Learning for Intelligent Fault Diagnosis},
year = {2019},
publisher = {GitHub},
journal = {GitHub repository},
howpublished = {\url{https://github.com/ZhaoZhibin/UDTL}},
}
```

## Contact
- dsym2894@yonsei.ac.kr