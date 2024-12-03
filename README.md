aw-importer-ical
==================

This extension imports data from ical files by watching a folder for changes.

There is already a [watcher](https://github.com/ActivityWatch/aw-import-ical) that imports ical files, but it has some problems. For example, it doesn't handle recurring events. It also is kind of old, so it might not work out of the box. It supports only one calendar per file too. If the calendar already exists, it will delete the bucket and try again. One thing that this watcher is missing related to that other watcher is a live connection to google calendar, but I am not a fan of live connections when data imports work okay. I just find these live connections to be a bit risky and I don't want to have to deal with them.


This watcher is currently in a early stage of development, please submit PRs if you find bugs!


## Usage

### Step 1: Install package

Install the requirements:

```sh
pip install .
```

First run (generates empty config that you need to fill out):
```sh
python aw-importer-ical/main.py
```

### Step 2: Enter config

You will need to add the path to the folder where you will add the .ics files. You can also update the polling time. 

### Step 3: Add the ical files to the folder

### Step 4: Restart the server and enable the watcher

Note: it might take a while to churn though all the data the first time or two depending on how many events you have. Once it is imported, it will not re-import the file (it will change the name of imported files) or re-import individual events based on the uid.


