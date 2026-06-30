"""
Expected Free-Energy Policy Selection with Allostatic Prior Shifting
Paradigm: interoceptive-active-inference

Implements discrete Bayesian active inference with:
- Expected free energy G(π) policy evaluation (pragmatic + epistemic terms)
- Allostatic prior shifting based on resource richness
- Dirichlet-based transition model learning
- Bayesian state inference over discretized state space
"""

import math
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _softmax(logits: list) -> list:
    max_l = max(logits)
    exps = [math.exp(l - max_l) for l in logits]
    s = sum(exps)
    return [e / s for e in exps]


def _normalize(vec: list) -> list:
    s = sum(vec)
    if s < 1e-12:
        n = len(vec)
        return [1.0 / n] * n
    return [v / s for v in vec]


def _entropy(col: list) -> float:
    """Shannon entropy of a probability vector (one column of A)."""
    h = 0.0
    for p in col:
        if p > 1e-12:
            h -= p * math.log(p + 1e-12)
    return h


class ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel:
    """
    Active inference agent that selects actions by minimising expected free energy G(π).

    State space: (dist_bin, energy_bin) with n_dist=4, n_energy=5 → 20 states.
    Observation space: same discretisation (near-identity likelihood).
    """

    # Canonical action set
    ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

    def __init__(
        self,
        mu_p_base: float = 0.8,
        mu_p_low: float = 0.5,
        lambda_allo: float = 0.1,
        w_prag: float = 1.0,
        w_epist: float = 0.5,
        T: int = 3,
        beta_G: float = 4.0,
        alpha_learn: float = 0.05,
        n_energy: int = 5,
        n_dist: int = 4,
        eta: float = 4.0,
        K_policies: int = 18,
        c_move: float = 0.05,
        c_stay: float = 0.02,
        k_eat: float = 0.3,
        seed: Optional[int] = None,
    ):
        # Parameters
        self.mu_p_base = mu_p_base
        self.mu_p_low = mu_p_low
        self.lambda_allo = lambda_allo
        self.w_prag = w_prag
        self.w_epist = w_epist
        self.T = T
        self.beta_G = beta_G
        self.alpha_learn = alpha_learn
        self.n_energy = n_energy
        self.n_dist = n_dist
        self.eta = eta
        self.K_policies = K_policies
        self.c_move = c_move
        self.c_stay = c_stay
        self.k_eat = k_eat

        if seed is not None:
            random.seed(seed)

        # State variables
        self.energy: float = 0.5
        self.mu_p: float = mu_p_base
        self.rho: float = 0.0

        # Discretised dimensions
        self.n_states = n_dist * n_energy   # 20
        self.n_obs = n_dist * n_energy      # same

        # Energy bin centres for preference computation
        self.energy_bin_centers = [0.1, 0.3, 0.5, 0.7, 0.9]

        # Flat observation / state indices
        # index = dist_bin * n_energy + energy_bin
        # q_s: posterior over hidden states (length n_states)
        self.q_s: list = [1.0 / self.n_states] * self.n_states

        # Preference vector C (length n_obs) — log preferences over observations
        self.C: list = self._compute_C(self.mu_p)

        # Likelihood matrix A: n_obs × n_states
        # Near-identity: A[o, s] = 0.9 if o==s, else 0.1/(n_states-1)
        self.A: list = self._init_A()

        # Transition model Dirichlet counts: dict action → n_states × n_states
        self.b_counts: dict = {
            a: [[1.0] * self.n_states for _ in range(self.n_states)]
            for a in self.ACTIONS
        }
        # Normalise to get B
        self.B: dict = {
            a: self._normalise_B(self.b_counts[a])
            for a in self.ACTIONS
        }

        # Memory of previous observation tuple (dist_bin, energy_bin)
        self.prev_obs: Optional[tuple] = None
        self.prev_action: Optional[str] = None

        # G values for last policy evaluation (for get_state q_values)
        self.q_values: dict = {a: 0.0 for a in self.ACTIONS}

        # Current observation tuple
        self.o_t: Optional[tuple] = None

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_A(self) -> list:
        """Near-identity likelihood matrix A (n_obs × n_states)."""
        n = self.n_states
        noise = 0.1 / max(1, n - 1)
        A = []
        for o in range(n):
            row = [noise] * n
            row[o] = 0.9
            A.append(row)
        return A

    def _normalise_B(self, counts: list) -> list:
        """Normalise each column of a count matrix to get a transition matrix."""
        n = self.n_states
        B = [[0.0] * n for _ in range(n)]
        for col in range(n):
            col_sum = sum(counts[row][col] for row in range(n))
            for row in range(n):
                B[row][col] = counts[row][col] / max(1e-12, col_sum)
        return B

    def _compute_C(self, mu_p: float) -> list:
        """R3: Preference vector C over observations = -eta * (e_center - mu_p)^2."""
        C = []
        for dist_bin in range(self.n_dist):
            for e_bin in range(self.n_energy):
                e_center = self.energy_bin_centers[e_bin]
                C.append(-self.eta * (e_center - mu_p) ** 2)
        return C

    # ------------------------------------------------------------------
    # Discretisation helpers
    # ------------------------------------------------------------------

    def _energy_bin(self) -> int:
        """Discretise energy into n_energy bins."""
        return min(self.n_energy - 1, int(self.energy * self.n_energy))

    def _dist_bin(self, dist: float) -> int:
        """Discretise distance: 0 (at), 1 (near 1-2), 2 (medium 3-5), 3 (far 6+)."""
        if dist == 0:
            return 0
        elif dist <= 2:
            return 1
        elif dist <= 5:
            return 2
        else:
            return 3

    def _obs_index(self, obs_tuple: tuple) -> int:
        dist_bin, e_bin = obs_tuple
        return dist_bin * self.n_energy + e_bin

    def _encode_observation(self, pos: tuple, food_list: list, grid_w: int, grid_h: int) -> tuple:
        """R4: Encode current perception into (dist_bin, energy_bin)."""
        if food_list:
            dists = [abs(pos[0] - f['x']) + abs(pos[1] - f['y']) for f in food_list]
            nearest_dist = min(dists)
        else:
            nearest_dist = grid_w + grid_h
        db = self._dist_bin(nearest_dist)
        eb = self._energy_bin()
        return (db, eb)

    # ------------------------------------------------------------------
    # Matrix operations
    # ------------------------------------------------------------------

    def _matvec(self, mat: list, vec: list) -> list:
        """Matrix × vector: mat is n×n, vec is n, result is n."""
        n = len(vec)
        result = []
        for row in range(n):
            result.append(sum(mat[row][col] * vec[col] for col in range(n)))
        return result

    def _mat_col(self, mat: list, col: int) -> list:
        """Extract column col from matrix."""
        return [mat[row][col] for row in range(len(mat))]

    # ------------------------------------------------------------------
    # Bayesian state inference (R5)
    # ------------------------------------------------------------------

    def _bayesian_update(self, o_t: tuple, prev_action: Optional[str]) -> list:
        """R5: Predict + update posterior."""
        if prev_action is not None:
            predicted = self._matvec(self.B[prev_action], self.q_s)
        else:
            predicted = self.q_s[:]

        o_idx = self._obs_index(o_t)
        likelihood = self.A[o_idx]  # row o_idx of A = P(o | s) for each s
        unnorm = [likelihood[s] * predicted[s] for s in range(self.n_states)]
        return _normalize(unnorm)

    # ------------------------------------------------------------------
    # Policy generation (R6)
    # ------------------------------------------------------------------

    def _get_move_toward(self, pos: tuple, food_list: list) -> str:
        """Heuristic: direction that minimises distance to nearest food."""
        if not food_list:
            return "stay"
        dists = [abs(pos[0] - f['x']) + abs(pos[1] - f['y']) for f in food_list]
        nearest = food_list[dists.index(min(dists))]
        dx = nearest['x'] - pos[0]
        dy = nearest['y'] - pos[1]
        if abs(dx) >= abs(dy):
            return "move_right" if dx > 0 else "move_left"
        else:
            return "move_down" if dy > 0 else "move_up"

    def _enumerate_policies(self, pos: tuple, food_list: list) -> list:
        """R6: Generate K candidate policies of length T."""
        move_toward = self._get_move_toward(pos, food_list)
        policies = []
        for first_action in self.ACTIONS:
            # Continuation (a): repeat same action
            policies.append([first_action] * self.T)
            # Continuation (b): first_action, then move_toward, then eat
            if self.T >= 2:
                cont_b = [first_action] + [move_toward] * (self.T - 2) + ["eat"]
            else:
                cont_b = [first_action]
            policies.append(cont_b)
            # Continuation (c): first_action, then move_toward, then stay
            if self.T >= 2:
                cont_c = [first_action] + [move_toward] * (self.T - 2) + ["stay"]
            else:
                cont_c = [first_action]
            policies.append(cont_c)
        return policies  # 6 × 3 = 18 policies

    # ------------------------------------------------------------------
    # Expected free energy (R7)
    # ------------------------------------------------------------------

    def _compute_G(self, policy: list, q_s_start: list) -> float:
        """R7: Compute expected free energy G(π) for a given policy."""
        G = 0.0
        q_future = q_s_start[:]
        n_states = self.n_states
        n_obs = self.n_obs

        for tau in range(len(policy)):
            action = policy[tau]
            # Predict future state distribution
            q_future = self._matvec(self.B[action], q_future)

            # Predicted observation distribution: q_obs = A @ q_future
            q_obs = []
            for o in range(n_obs):
                val = sum(self.A[o][s] * q_future[s] for s in range(n_states))
                q_obs.append(val)

            # Pragmatic term: KL(q_obs || preference)
            # = sum q_obs[o] * (log q_obs[o] - C[o])
            pragmatic = 0.0
            for o in range(n_obs):
                if q_obs[o] > 1e-12:
                    pragmatic += q_obs[o] * (math.log(q_obs[o] + 1e-12) - self.C[o])

            # Epistemic term: negative expected ambiguity
            # ambiguity = sum_s q_future[s] * H(A[:, s])
            ambiguity = 0.0
            for s in range(n_states):
                if q_future[s] > 1e-12:
                    col = [self.A[o][s] for o in range(n_obs)]
                    h = _entropy(col)
                    ambiguity += q_future[s] * h
            epistemic = -ambiguity  # negative ambiguity = information gain

            G += self.w_prag * pragmatic + self.w_epist * epistemic

        return G

    # ------------------------------------------------------------------
    # decide (READ-ONLY)
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """R4 → R5 → R6 → R7 → R8: select action from current state."""
        pos = (perception['x'], perception['y'])
        food_list = perception.get('resources', {}).get('food', [])
        grid_w = perception['grid_width']
        grid_h = perception['grid_height']

        # R4: encode observation using current energy
        o_t = self._encode_observation(pos, food_list, grid_w, grid_h)

        # R5: Bayesian state inference
        q_s_updated = self._bayesian_update(o_t, self.prev_action)

        # R6: enumerate policies
        policies = self._enumerate_policies(pos, food_list)

        # R7: evaluate G for each policy
        G_vals = []
        for policy in policies:
            G_vals.append(self._compute_G(policy, q_s_updated))

        # R8: softmax policy selection
        logits = [-self.beta_G * g for g in G_vals]
        probs = _softmax(logits)

        # Weighted random sample
        r = random.random()
        cumsum = 0.0
        chosen_idx = len(policies) - 1
        for i, p in enumerate(probs):
            cumsum += p
            if r <= cumsum:
                chosen_idx = i
                break

        selected_policy = policies[chosen_idx]
        selected_action = selected_policy[0]

        # Store for next update (do NOT mutate self.q_s here)
        self._pending_q_s = q_s_updated
        self._pending_o_t = o_t
        self._pending_G_vals = G_vals
        self._pending_policies = policies

        return Action(name=selected_action)

    # ------------------------------------------------------------------
    # update (WRITE)
    # ------------------------------------------------------------------

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """Apply R1, R2, R3, R5 state commits, and R9 transition learning."""
        action_name = action.name
        food_list = new_perception.get('resources', {}).get('food', [])
        grid_w = new_perception['grid_width']
        grid_h = new_perception['grid_height']
        pos = (new_perception['x'], new_perception['y'])
        lar = new_perception.get('last_action_result', {})

        # R1: Energy dynamics
        if action_name == 'eat':
            consumed = lar.get('consumed', False) or lar.get('success', False)
            if consumed:
                palatability = lar.get('palatability', 1.0)
                self.energy = min(1.0, max(0.0, self.energy + self.k_eat * palatability))
            else:
                self.energy = min(1.0, max(0.0, self.energy - self.c_stay))
        elif action_name in ('move_up', 'move_down', 'move_left', 'move_right'):
            self.energy = min(1.0, max(0.0, self.energy - self.c_move))
        else:  # stay
            self.energy = min(1.0, max(0.0, self.energy - self.c_stay))

        # R2: Allostatic prior update
        visible_cell_count = max(1, grid_w * grid_h)
        self.rho = len(food_list) / visible_cell_count
        target = self.rho * self.mu_p_base + (1 - self.rho) * self.mu_p_low
        self.mu_p = self.mu_p + self.lambda_allo * (target - self.mu_p)

        # R3: Recompute preference vector
        self.C = self._compute_C(self.mu_p)

        # Commit state posterior from decide (pending)
        if hasattr(self, '_pending_q_s'):
            self.q_s = self._pending_q_s
            self.o_t = self._pending_o_t

        # R9: Transition model learning
        new_o = self._encode_observation(pos, food_list, grid_w, grid_h)
        if self.prev_obs is not None:
            s_old_idx = self._obs_index(self.prev_obs)
            s_new_idx = self._obs_index(new_o)
            counts = self.b_counts[action_name]
            counts[s_new_idx][s_old_idx] += self.alpha_learn
            # Renormalise column s_old_idx
            col_sum = sum(counts[row][s_old_idx] for row in range(self.n_states))
            for row in range(self.n_states):
                self.B[action_name][row][s_old_idx] = counts[row][s_old_idx] / max(1e-12, col_sum)

        # Update q_values for get_state (action-level: average G over policies starting with each action)
        if hasattr(self, '_pending_G_vals') and hasattr(self, '_pending_policies'):
            action_G = {a: [] for a in self.ACTIONS}
            for policy, g in zip(self._pending_policies, self._pending_G_vals):
                action_G[policy[0]].append(g)
            # q_value = negative average G (higher = better)
            for a in self.ACTIONS:
                if action_G[a]:
                    self.q_values[a] = -sum(action_G[a]) / len(action_G[a])
                else:
                    self.q_values[a] = 0.0

        # Advance history
        self.prev_obs = new_o
        self.prev_action = action_name

    # ------------------------------------------------------------------
    # get_state
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "energy": self.energy,
            "mu_p": self.mu_p,
            "rho": self.rho,
            "o_t": self.o_t,
            "q_s": self.q_s[:],
            "C": self.C[:],
            "prev_action": self.prev_action,
            "prev_obs": self.prev_obs,
            "q_values": dict(self.q_values),
        }
