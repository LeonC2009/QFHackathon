# Modular Setup Backup

The original multi-file implementation remains intact as the maintained backup/reference setup.

Key entry points:

- `universe.py`: EIA and Yahoo universe loading
- `qubo.py`: QUBO, Ising, feasibility, and exact solver logic
- `qaoa_solver.py`: local Qrisp adapter
- `run_pipeline.py`: modular end-to-end workflow
- `run_on_quantum.py`: IQM Resonance/Garnet adapter
- `dashboard/` and `dashboard_server.py`: modular dashboard
- `project_data/download_yahoo_futures.py`: Yahoo data downloader

The convenience entry point is `qfhackathon_all_in_one.py`. It does not replace or delete these files.
