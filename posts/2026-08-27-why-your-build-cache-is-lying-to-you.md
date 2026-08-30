---
title: Why your build cache is lying to you
date: 2026-08-27
tags: systems, tooling
snippet: A deep dive into cache invalidation edge cases that took down three separate CI pipelines last month, and the one-line fix that would have prevented all of it.
---

Caching is supposed to make builds faster, not lie to you about what's actually in your artifacts. But that's exactly what happened when a stale hash comparison let three separate CI pipelines ship outdated bundles for almost a week.

## The setup

Most build caches key off file contents, not file paths. That's usually the right call — it means renaming a file without changing its contents doesn't trigger an unnecessary rebuild. But it has a sharp edge.

If two files in different directories happen to produce the same hash of *their inputs* (not their outputs), a naive cache can serve the wrong artifact entirely.

## What actually broke

```
$ diff cached-output.js fresh-output.js
diff: files differ (but hashes matched)
```

The cache key didn't include the build **target**, only the source contents. Two configs pointing at the same source file, but compiling for different environments, collided on the same cache entry.

> Lesson: a cache key is a promise about equivalence. Make sure it actually captures everything that affects the output.

The fix was one line: include the target environment in the cache key. Three days of debugging, one line of code.

- Always hash your *effective* inputs, not just the files on disk
- Include environment/target flags in any cache key
- When in doubt, add a manual "bust cache" escape hatch
