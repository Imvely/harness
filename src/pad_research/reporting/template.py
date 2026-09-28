"""Markdown template for experiment reports.

The heading structure mirrors research contract §44 exactly. Body text is
Korean because reports are research documents in this repository.
"""

from __future__ import annotations

from string import Template

SECTION44_HEADINGS: tuple[str, ...] = (
    "# Experiment Report",
    "## Research Question",
    "## Hypothesis",
    "## Protocol",
    "## Model",
    "## Training",
    "## Results",
    "### Overall",
    "### Per Attack",
    "## Security Regression Check",
    "## Seed Variance",
    "## Failure Analysis",
    "## Interpretation",
    "## What This Does NOT Prove",
    "## Next Experiment",
    "## MLflow Runs",
    "## Git Commit",
)

REPORT_TEMPLATE = Template(
    """# Experiment Report

$banners

## Research Question

$research_question

## Hypothesis

$hypothesis

## Protocol

$protocol

## Model

$model

## Training

$training

## Results

### Overall

$overall_table

### Per Attack

$per_attack_table

## Security Regression Check

$security_regression

## Seed Variance

$seed_variance

## Failure Analysis

$failure_analysis

## Interpretation

$interpretation

## What This Does NOT Prove

$does_not_prove

## Next Experiment

$next_experiment

## MLflow Runs

$mlflow_runs

## Git Commit

$git_commit
"""
)
