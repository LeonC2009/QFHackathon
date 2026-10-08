# ==========================================
# 1. INSTALL DEPENDENCIES IN COLAB
# ==========================================
# Install the exact packages required to communicate with IQM Resonance
#!pip install "iqm-client[qiskit]" qiskit numpy scipy -q

import os
import json
import numpy as np
from qiskit.circuit.library import QAOAAnsatz
from qiskit.quantum_info import SparsePauliOp
from qiskit import transpile
from iqm.qiskit_iqm import IQMProvider

# ==========================================
# 2. SET UP IQM RESONANCE CREDENTIALS
# ==========================================
# Paste your token from the IQM Resonance Dashboard here
IQM_TOKEN = "YOUR_IQM_RESONANCE_TOKEN"
IQM_URL = "https://resonance.iqm.tech"

try:
    provider = IQMProvider(IQM_URL, token=IQM_TOKEN)
    backend = provider.get_backend("garnet")
    print(f"✅ Successfully connected to IQM Resonance QPU: {backend.name}")
except Exception as e:
    print(f"❌ Connection failed! Verify your token credential string: {e}")
    raise e

# ==========================================
# 3. LOAD THE NPZ FILE AND BUILD H AND J
# ==========================================
# This reads the ising.npz file you uploaded into the Colab file tree
if not os.path.exists("ising.npz"):
    raise FileNotFoundError("Could not find 'ising.npz' in the Colab file list. Please drag-and-drop it into the files panel.")

data = np.load("ising.npz")
h, J, offset = data['h'], data['J'], data['offset']
n = len(h)

# Convert h and J matrix into Qiskit's SparsePauliOp
pauli_list = []
# Linear terms (h_i * Z_i)
for i in range(n):
    if abs(h[i]) > 1e-6:
        op_str = ["I"] * n
        op_str[i] = "Z"
        pauli_list.append(("".join(op_str), h[i]))

# Quadratic terms (J_ij * Z_i * Z_j)
for i in range(n):
    for j in range(i + 1, n):
        if abs(J[i, j]) > 1e-6:
            op_str = ["I"] * n
            op_str[i] = "Z"
            op_str[j] = "Z"
            pauli_list.append(("".join(op_str), J[i, j]))

hamiltonian = SparsePauliOp.from_list(pauli_list)

# ==========================================
# 4. CONSTRUCT AND TRANSPILE THE QAOA CIRCUIT
# ==========================================
reps = 1
qaoa_circuit = QAOAAnsatz(cost_operator=hamiltonian, reps=reps)
qaoa_circuit.measure_all()

print("Routing and transpiling the asset interaction grid to match Garnet's hardware architecture...")
transpiled_circuit = transpile(qaoa_circuit, backend=backend, optimization_level=3)

# ==========================================
# 5. SUBMIT TO THE PHYSICAL HARDWARE QUEUE
# ==========================================
# Bind sample trial parameters (gamma=0.5, beta=0.5) for a quick optimization pass
initial_angles = [0.5] * (2 * reps)
parameter_binds = dict(zip(qaoa_circuit.parameters, initial_angles))
bound_circuit = transpiled_circuit.assign_parameters(parameter_binds)

print(f"Uploading job queue packet to {backend.name}...")
# 1000 or up to 20,000 shots depending on your time constraints
job = backend.run(bound_circuit, shots=1000) 
result = job.result()
counts = result.get_counts()

# Calculate shot probabilities
total_shots = sum(counts.values())
probabilities = {bitstr: count / total_shots for bitstr, count in counts.items()}

# ==========================================
# 6. EXPORT THE GENERATED DATA
# ==========================================
with open("iqm_raw_results.json", "w") as f:
    json.dump(probabilities, f, indent=4)

print("🎉 Job complete! Results saved to 'iqm_raw_results.json' inside your Colab file folder.")
