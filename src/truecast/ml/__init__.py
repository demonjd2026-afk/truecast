"""Trained models: live win probability and shot xG.

Models are trained offline (scikit-learn) on simulated matches and deployed as
compact JSON artifacts; runtime inference here is pure-Python, so the live
service needs no heavy ML dependency. See ml/train.py and the metrics it prints.
"""
