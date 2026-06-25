# version_2  — frozen 2026-06-24 (iteration 2)
Coverage-reward iteration. R_suspector = ( Σ confidence over CONFIRMED ) · 0.9^(unseen_files).
Genome change: INVESTIGATE_REPO_SYS now states the reward as a per-file coverage gradient
(each unread source file ≈ −10%). Diff: INVESTIGATE_REPO_SYS only; rest identical to current_version at freeze.
version_1 (2026-06-14) = pre-coverage baseline.
