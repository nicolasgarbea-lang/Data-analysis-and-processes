# B config.yaml explained

<div class="inshort" markdown="1">

`config.yaml` is the single source of settings; every script reads it through `src/config.py`. The table below is
generated from the file itself, line by line: the key, its value, the comment in the file, what it means, and which
source files read it (found by searching for the key name).

</div>

{{t:config|Every setting in `config.yaml`. "Read in" lists the files that contain the key name in quotes; settings read through a whole section (e.g. `battery`) may not show every user.}}

**Two things to remember.**

- The `bidding` section holds the plain **defaults**. The backtest and the app use the settings **tuned** on data
  before October, stored in `reports/decision_tuning.csv` (chosen: {{n:tune_chosen}}).
- Changing `periods` changes what "train", "validation" and "test" mean. Any change after the test month has been
  looked at breaks the protocol; record it in the review log.
