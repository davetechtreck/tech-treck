---
title: I benchmarked every linter so you don't have to
date: 2026-08-12
tags: tooling
snippet: Turns out the fastest one isn't the one everyone's using.
---

Every few months someone claims their linter is "blazing fast." So I actually timed six of them against the same 40,000-file codebase.

## The results

The tool most teams reach for by default landed in the middle of the pack. The fastest option was a newer, less popular linter written in a compiled language rather than running on a VM — no surprise there, but the gap was bigger than expected: **roughly 9x** on a cold run.

## The catch

Speed isn't the only variable. Plugin ecosystem, editor integration, and how many of your existing rules are already ported over all matter more than raw benchmark numbers for most day-to-day use.

If your lint step is currently the bottleneck in CI, though, it's worth the migration. If it's not, this is a classic case of optimizing something that was never actually slow enough to matter.
