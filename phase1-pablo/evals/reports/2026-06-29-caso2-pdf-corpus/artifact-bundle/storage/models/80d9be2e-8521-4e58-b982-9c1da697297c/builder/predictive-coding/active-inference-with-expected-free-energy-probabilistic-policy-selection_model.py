"""
Active Inference with Expected Free Energy (Probabilistic Policy Selection)

Full active inference agent using expected free energy (EFE) for policy selection.
Maintains categorical beliefs over discrete hidden states, updates beliefs via
Bayesian filtering with a learned likelihood matrix A and deterministic transition
matrices B. Actions are evaluated by their expected free energy decomposed into
pragmatic (goal-directed) and epistemic (curiosity/exploration) components.
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


class ActiveInferenceWithExpectedFreeEnergyProbabilisticPolicySelectionModel:
    """
    Active inference agent with expected free energy policy selection.

    Hidden states: K = 50  (25 cells in a 5×5 local grid  × 2 food states)
    Observations:  N_obs = 8  (4 food-proximity × 2 ate-states)
    Actions:       move_up, move_down, move_left, move_right, stay, eat
    """

    # ------------------------------------------------------------------ #
    #  Grid layout helpers                                                 #
    # ------------------------------------------------------------------ #
    # Local 5×5 grid, row-major. Cell index = row*5 + col
    # Center cell index = 12  (row 2, col 2)
    LOCAL_GRID_SIZE = 5
    CENTER_IDX = 12  # (2, 2) in a 5×5 grid
    N_LOCAL_CELLS = 25

    ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

    # Action deltas on the local grid (row, col)
    ACTION_DELTA = {
        "move_up":    (-1, 0),
        "move_down":  (1, 0),
        "move_left":  (0, -1),
        "move_right": (0, 1),
        "stay":       (0, 0),
        "eat":        (0, 0),
    }

    def __init__(
        self,
        beta_G: float = 4.0,
        omega: float = 0.5,
        alpha_H: float = 0.05,
        delta_H: float = 0.4,
        H_star: float = 0.0,
        K: int = 50,
        N_obs: int = 8,
        alpha_B: float = 0.05,
        sigmoid_scale: float = 0.1,
        seed: int = None,
    ):
        # ---- Parameters ----
        self.beta_G = beta_G
        self.omega = omega
        self.alpha_H = alpha_H
        self.delta_H = delta_H
        self.H_star = H_star
        self.K = K
        self.N_obs = N_obs
        self.alpha_B = alpha_B
        self.sigmoid_scale = sigmoid_scale

        if seed is not None:
            random.seed(seed)

        # ---- State variables ----
        self.o = 7                          # current observation index
        self.H = 0.3                        # hunger
        self.s_belief = [1.0 / K] * K      # posterior over hidden states
        self.s_prior = [1.0 / K] * K       # prior (predicted state distribution)
        self.eps = [0.0] * N_obs            # prediction error
        self.G = 0.0
        self.G_prag = 0.0
        self.G_epist = 0.0
        self.a = "stay"

        # Preferred outcomes (initialised via hunger)
        self.C = self._compute_preferred_outcomes(self.H)

        # ---- Likelihood matrix A[o][k]: N_obs × K ----
        self.A = self._init_A()

        # ---- Transition matrices B[action][k'][k]: per-action K × K ----
        self.B = self._init_B()

        # ---- Precomputed: states where food is at center cell ----
        # State index: k = cell_idx * 2 + food_present_flag
        #   food_present_flag = 1 → food present; 0 → food absent
        self.food_at_center_states = [
            self._state_idx(self.CENTER_IDX, 1)
        ]

        # ---- q_values cache ----
        self.q_values: dict = {a: 0.0 for a in self.ACTIONS}

    # ================================================================== #
    #  Helpers                                                             #
    # ================================================================== #

    @staticmethod
    def _sigmoid(x: float) -> float:
        # Numerically stable
        if x >= 0:
            return 1.0 / (1.0 + math.exp(-x))
        else:
            e = math.exp(x)
            return e / (1.0 + e)

    @staticmethod
    def _clip(val: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, val))

    @staticmethod
    def _state_idx(cell_idx: int, food_flag: int) -> int:
        """Encode (cell_idx, food_flag) → state index in [0, K)."""
        return cell_idx * 2 + food_flag

    @staticmethod
    def _state_decode(k: int):
        """Decode state index k → (cell_idx, food_flag)."""
        return k // 2, k % 2

    def _cell_neighbors_at_center(self) -> list:
        """Return cell indices that are Manhattan-distance 1 from center."""
        cr, cc = divmod(self.CENTER_IDX, self.LOCAL_GRID_SIZE)
        neighbors = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = cr + dr, cc + dc
            if 0 <= nr < self.LOCAL_GRID_SIZE and 0 <= nc < self.LOCAL_GRID_SIZE:
                neighbors.append(nr * self.LOCAL_GRID_SIZE + nc)
        return neighbors

    def _init_A(self) -> list:
        """
        Initialize likelihood matrix A[o][k] from grid topology.

        Observation codes:
          0: food_here  + just_ate
          1: food_here  + not_ate
          2: food_adj   + just_ate
          3: food_adj   + not_ate
          4: food_vis   + just_ate  (visible_far ≡ visible in 5×5 local grid)
          5: food_vis   + not_ate
          6: no_food    + just_ate
          7: no_food    + not_ate
        """
        N, K = self.N_obs, self.K
        A = [[0.0] * K for _ in range(N)]

        adj_cells = set(self._cell_neighbors_at_center())
        center = self.CENTER_IDX

        for k in range(K):
            cell_idx, food_flag = self._state_decode(k)
            if food_flag == 1:  # food present somewhere in the local grid
                if cell_idx == center:
                    # food right here
                    A[1][k] = 0.80   # food_here + not_ate
                    A[0][k] = 0.10   # food_here + just_ate  (rarely "just ate" purely from state)
                    A[3][k] = 0.05   # food_adj + not_ate
                    A[7][k] = 0.05
                elif cell_idx in adj_cells:
                    A[3][k] = 0.70   # food_adj + not_ate
                    A[2][k] = 0.05
                    A[5][k] = 0.10
                    A[1][k] = 0.05
                    A[7][k] = 0.10
                else:
                    # food visible but far
                    A[5][k] = 0.60   # food_vis + not_ate
                    A[4][k] = 0.05
                    A[7][k] = 0.25
                    A[3][k] = 0.10
            else:
                # no food in this cell
                A[7][k] = 0.80   # no_food + not_ate
                A[6][k] = 0.05
                A[5][k] = 0.05
                A[3][k] = 0.05
                A[1][k] = 0.05

        # Normalize columns so each sums to 1
        for k in range(K):
            col_sum = sum(A[o][k] for o in range(N))
            if col_sum > 1e-12:
                for o in range(N):
                    A[o][k] /= col_sum
            else:
                # fallback: uniform
                for o in range(N):
                    A[o][k] = 1.0 / N

        return A

    def _init_B(self) -> dict:
        """
        Build action-conditioned transition matrices B[action][k'][k].

        State index: k = cell_idx * 2 + food_flag
        For movement actions: shift local-grid center by action delta.
          - If shifted cell goes out of local 5×5 grid, state maps to the
            same cell (boundary clamping).
        For stay: B = identity.
        For eat: food at center → transitions to food-absent at center.
                 All other states stay identical.
        """
        K = self.K
        G = self.LOCAL_GRID_SIZE
        B = {}

        for action in self.ACTIONS:
            mat = [[0.0] * K for _ in range(K)]

            if action == "stay":
                for k in range(K):
                    mat[k][k] = 1.0

            elif action == "eat":
                for k in range(K):
                    cell_idx, food_flag = self._state_decode(k)
                    if cell_idx == self.CENTER_IDX and food_flag == 1:
                        # food consumed → same cell, food absent
                        k_prime = self._state_idx(self.CENTER_IDX, 0)
                        mat[k_prime][k] = 1.0
                    else:
                        mat[k][k] = 1.0

            else:
                dr, dc = self.ACTION_DELTA[action]
                for k in range(K):
                    cell_idx, food_flag = self._state_decode(k)
                    row, col = divmod(cell_idx, G)
                    new_row = max(0, min(G - 1, row + dr))
                    new_col = max(0, min(G - 1, col + dc))
                    new_cell_idx = new_row * G + new_col
                    k_prime = self._state_idx(new_cell_idx, food_flag)
                    mat[k_prime][k] = 1.0

            B[action] = mat

        return B

    def _compute_preferred_outcomes(self, H: float) -> list:
        """
        Compute hunger-modulated preferred outcome distribution C (R5).
        When H is high, food-related observations are strongly preferred.
        """
        food_pref = self._sigmoid(H / self.sigmoid_scale)

        C = [0.0] * self.N_obs
        C[0] = food_pref * 0.50   # food_here + just_ate
        C[1] = food_pref * 0.30   # food_here + not_ate
        C[2] = food_pref * 0.10   # food_adj  + just_ate
        C[3] = food_pref * 0.05   # food_adj  + not_ate
        remaining = max(1.0 - sum(C[:4]), 0.01)
        n_rest = self.N_obs - 4
        for i in range(4, self.N_obs):
            C[i] = remaining / n_rest

        total_C = sum(C)
        return [c / total_C for c in C]

    @staticmethod
    def _encode_observation(
        food_here: bool,
        food_adjacent: bool,
        food_visible: bool,
        just_ate: bool,
    ) -> int:
        """
        Map (food_proximity, just_ate) → discrete observation index 0..7.

        0: food_here     + just_ate
        1: food_here     + not_ate
        2: food_adjacent + just_ate
        3: food_adjacent + not_ate
        4: food_visible  + just_ate
        5: food_visible  + not_ate
        6: no_food       + just_ate
        7: no_food       + not_ate
        """
        if food_here:
            return 0 if just_ate else 1
        elif food_adjacent:
            return 2 if just_ate else 3
        elif food_visible:
            return 4 if just_ate else 5
        else:
            return 6 if just_ate else 7

    def _perception_to_observation(self, perception: dict) -> int:
        """Extract discrete observation index from raw perception."""
        food_sources = perception.get("resources", {}).get("food", [])
        ax, ay = perception["x"], perception["y"]
        last_result = perception.get("last_action_result", {})
        just_ate = (
            last_result.get("consumed", False)
            if isinstance(last_result, dict)
            else False
        )

        food_here = any(
            f["x"] == ax and f["y"] == ay for f in food_sources
        )
        food_adjacent = any(
            abs(f["x"] - ax) + abs(f["y"] - ay) == 1 for f in food_sources
        )
        food_visible = any(
            abs(f["x"] - ax) + abs(f["y"] - ay) <= 5 for f in food_sources
        )

        return self._encode_observation(food_here, food_adjacent, food_visible, just_ate)

    def _bayesian_update(self, o_obs: int) -> list:
        """R3: Bayesian belief update."""
        K = self.K
        numerator = [self.A[o_obs][k] * self.s_prior[k] for k in range(K)]
        Z = sum(numerator)
        if Z > 1e-10:
            return [n / Z for n in numerator]
        else:
            return [1.0 / K] * K

    def _predict_next_state(self, action: str, s_belief: list) -> list:
        """R4: Propagate belief through transition model."""
        K = self.K
        B_a = self.B[action]
        s_next = [0.0] * K
        for k_prime in range(K):
            row_sum = 0.0
            for k in range(K):
                row_sum += B_a[k_prime][k] * s_belief[k]
            s_next[k_prime] = row_sum
        return s_next

    def _compute_efe(self, action: str, s_belief: list, C: list) -> tuple:
        """
        Compute EFE for a single action.
        Returns (G_total, G_prag, G_epist).
        """
        K, N = self.K, self.N_obs
        A = self.A

        # Special case: penalise eat when food belief is very low
        if action == "eat":
            food_belief = sum(s_belief[k] for k in self.food_at_center_states)
            if food_belief < 0.1:
                return 100.0, 100.0, 0.0

        # Predict next state (R4)
        s_next = self._predict_next_state(action, s_belief)

        # Predicted observation distribution Q_o (R6 prerequisite)
        Q_o = [sum(A[o][k] * s_next[k] for k in range(K)) for o in range(N)]
        Q_sum = sum(Q_o)
        if Q_sum < 1e-12:
            Q_o = [1.0 / N] * N
        else:
            Q_o = [max(q / Q_sum, 1e-12) for q in Q_o]

        # R6: Pragmatic EFE — D_KL(Q_o || C)
        G_prag = 0.0
        for ob in range(N):
            if Q_o[ob] > 1e-12:
                G_prag += Q_o[ob] * math.log(Q_o[ob] / max(C[ob], 1e-12))

        # R7: Epistemic EFE — negative mutual information
        G_epist = 0.0
        for k in range(K):
            if s_next[k] > 1e-12:
                for ob in range(N):
                    if A[ob][k] > 1e-12:
                        G_epist -= s_next[k] * A[ob][k] * math.log(
                            A[ob][k] / Q_o[ob]
                        )

        # R8: Total EFE
        G_total = (1.0 - self.omega) * G_prag + self.omega * G_epist

        return G_total, G_prag, G_epist

    def _softmax_action_selection(self, G_values: dict) -> str:
        """R9: Sample action proportional to exp(-beta_G * G)."""
        action_list = list(G_values.keys())
        neg_G = [-G_values[a] for a in action_list]
        max_nG = max(neg_G)
        exp_vals = [math.exp(self.beta_G * (v - max_nG)) for v in neg_G]
        total = sum(exp_vals)
        probs = [e / total for e in exp_vals]

        r = random.random()
        cumulative = 0.0
        for action, p in zip(action_list, probs):
            cumulative += p
            if r <= cumulative:
                return action
        return action_list[-1]

    # ================================================================== #
    #  DecisionModel contract                                              #
    # ================================================================== #

    def decide(self, perception: dict) -> Action:
        """
        Read-only: select action using current internal state.
        Does NOT modify any state variables.
        """
        # Step 1: Compute preferred outcomes from current hunger
        C = self._compute_preferred_outcomes(self.H)

        # Step 2: Evaluate each candidate action
        G_values = {}
        for act in self.ACTIONS:
            G_total, _, _ = self._compute_efe(act, self.s_belief, C)
            G_values[act] = G_total

        # Step 3: Softmax action selection (R9)
        selected = self._softmax_action_selection(G_values)

        return Action(name=selected)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        Update all state variables after action execution.
        """
        act_name = action.name

        # --- Encode new observation ---
        o_obs = self._perception_to_observation(new_perception)
        self.o = o_obs

        # --- R10: Hunger dynamics ---
        ate = 1 if reward > 0 else 0
        self.H = self._clip(
            self.H + self.alpha_H - self.delta_H * ate, 0.0, 1.0
        )

        # --- R3: Bayesian belief update ---
        self.s_belief = self._bayesian_update(o_obs)

        # --- Compute prediction error (eps) ---
        pred_obs = [
            sum(self.A[ob][k] * self.s_prior[k] for k in range(self.K))
            for ob in range(self.N_obs)
        ]
        for ob in range(self.N_obs):
            if pred_obs[ob] > 1e-12:
                self.eps[ob] = math.log(
                    max(self.A[o_obs][ob], 1e-12) / pred_obs[ob]
                )
            else:
                self.eps[ob] = 0.0

        # --- R11: Likelihood matrix learning ---
        for k in range(self.K):
            self.A[o_obs][k] += self.alpha_B * self.s_belief[k] * (
                1.0 - self.A[o_obs][k]
            )
        # Renormalize columns of A
        for k in range(self.K):
            col_sum = sum(self.A[ob][k] for ob in range(self.N_obs))
            if col_sum > 1e-12:
                for ob in range(self.N_obs):
                    self.A[ob][k] /= col_sum

        # --- Propagate posterior as next prior (R4 for taken action) ---
        self.s_prior = self._predict_next_state(act_name, self.s_belief)

        # --- Update EFE state variables for get_state() ---
        C = self._compute_preferred_outcomes(self.H)
        new_G_values = {}
        for a in self.ACTIONS:
            G_total, G_p, G_e = self._compute_efe(a, self.s_belief, C)
            new_G_values[a] = G_total
            if a == act_name:
                self.G = G_total
                self.G_prag = G_p
                self.G_epist = G_e

        self.C = C
        self.a = act_name
        self.q_values = {a: -new_G_values[a] for a in self.ACTIONS}

    def get_state(self) -> dict:
        return {
            "o": self.o,
            "H": self.H,
            "G": self.G,
            "G_prag": self.G_prag,
            "G_epist": self.G_epist,
            "a": self.a,
            "s_belief": list(self.s_belief),
            "s_prior": list(self.s_prior),
            "eps": list(self.eps),
            "C": list(self.C),
            "q_values": dict(self.q_values),
        }
