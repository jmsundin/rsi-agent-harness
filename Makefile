.PHONY: test smoke ui data baseline loop reset

test:
	RATCHET_MOCK=1 python3 -m unittest discover -s tests

smoke:
	RATCHET_MOCK=1 python3 -m loop.run --generations 6 --run-id smoke

ui:
	python3 -m ui.server

data:
	python3 -m grader.data fetch

baseline:
	python3 -m eval.run --split train --runs 3
	python3 -m eval.run --split heldout --runs 1

loop:
	python3 -m loop.run --generations 30 --runs 2

# Return main to the gen-0 scaffold and drop loop artifacts (use with care).
reset:
	git branch --list 'cand/*' | xargs -r git branch -D
	git tag -l 'rejected/*' | xargs -r git tag -d
	git worktree prune
	rm -rf runs .worktrees CHANGELOG.md grader/data/noise.json
