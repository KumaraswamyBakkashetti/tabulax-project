# TabulaX: Leveraging LLMs for Multi-Class Table Transformations

**TabulaX** is an intelligent data transformation framework that uses large language models (LLMs) to handle diverse table transformations. It automates the integration of tabular data from heterogeneous sources by identifying the correct transformation class—string-based, numerical, algorithmic, or general—and generating interpretable, executable transformation functions.

---

## 📌 Table of Contents

- [Introduction](#introduction)
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Usage](#usage)
- [Datasets](#datasets)
- [Benchmarks](#benchmarks)
- [Limitations](#limitations)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

---

## 📖 Introduction

Data integration across varied tabular sources often fails due to formatting mismatches. Existing systems are limited in their ability to handle multiple transformation types and often lack interpretability.

**TabulaX** addresses these challenges using LLMs:
- Classifies table transformations into four categories.
- Applies specialized strategies per class.
- Generates interpretable transformation code (e.g., Python).
- Supports downstream tasks like heterogeneous joins, missing value imputation, and anomaly detection.

---

## ✨ Features

- 🔍 **Transformation Classification**: Categorizes source-target table relationships into String, Numeric, Algorithmic, and General types.
- 🧠 **LLM-Based Code Generation**: Produces human-readable transformation functions.
- 🔄 **Multi-Class Handling**: Supports string manipulations, unit conversions, date formatting, and semantic lookups.
- 📈 **Outperforms SOTA**: Demonstrates higher accuracy and broader applicability than DTT, GXJoin, and others.
- 📊 **Interpretable Output**: Generates transformation logic in the form of executable code for full transparency.

---

## 🏗 Architecture

```plaintext
             +-------------------+
             |   Input Tables    |
             +--------+----------+
                      |
                      v
              +---------------+
              | Transformation|
              |   Classifier  |
              +-------+-------+
                      |
    -------------------------------------------
    |             |               |           |
    v             v               v           v
 String-     Numerical      Algorithmic    General
Based        Mapping         Mapping       Mapping
            (Curve Fitting) (CoT-based)   (LLM Lookup)
    |             |               |           |
    +-------------+---------------+-----------+
                      |
                      v
            +---------------------+
            | Transformation Code |
            |   (Python Output)   |
            +---------------------+
                      |
                      v
         +-----------------------------+
         |  Downstream Applications    |
         | (Joins, Imputation, etc.)   |
         +-----------------------------+
