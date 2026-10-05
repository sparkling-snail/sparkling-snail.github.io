---
title: "SLO monitoring for the LTA Bus Arrival API"
summary: "SLOs, error budgets and multi-window burn-rate alerts for a public API, built with Prometheus, Grafana and Alertmanager."
glyph: "99.9"
weight: 30
tags: ["prometheus", "grafana", "slo", "fastapi", "docker-compose"]
repo: ""
---

## Problem

Defining reliability for a dependency you don't control: what "good" looks like for Singapore's bus arrival API, and how to alert on it without paging for every blip.

## What I built

- A FastAPI service that wraps the LTA Bus Arrival API and exports Prometheus metrics.
- SLIs and SLOs defined in PromQL, with error budget tracking in Grafana.
- Multi-window, multi-burn-rate alerts routed through Alertmanager.
- The whole stack runs with Docker Compose.

## What I learned

<!-- e.g. choosing burn-rate windows, false positives you tuned out. -->
