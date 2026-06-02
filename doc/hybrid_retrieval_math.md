# Hybrid Retrieval: Mathematical Explanation

This document explains the internal retrieval math used to merge **Vector (Semantic) Search** and **BM25 (Keyword) Search** scores.

---

## The Scale Mismatch Problem

*   **Vector Search** yields cosine similarity scores (typically between `0.0` and `1.0`).
*   **BM25 Search** yields term-frequency scores based on keyword density (unbounded, e.g., `0.0` to `10.0+`).

Directly adding these raw scores is impossible. If we computed `vector_score + bm25_score` directly, the BM25 score would completely dominate the final rank. 

To solve this, we use **Min-Max Normalisation** to scale both sets of scores to a uniform range of `[0.0, 1.0]` (representing `0%` to `100%`) before combining them.

---

## Step-by-Step Dummy Calculation

Let's assume we have a candidate pool of **3 documents** matching the query **"machine learning"**.

### Raw Retrieval Scores

| Document | Vector Similarity (Raw) | BM25 Score (Raw) | Description |
| :--- | :---: | :---: | :--- |
| **Doc A** | `0.85` | `6.0` | Perfect keyword match and highly relevant. |
| **Doc B** | `0.70` | `2.0` | Good keyword match, moderately relevant. |
| **Doc C** | `0.60` | `0.0` | No keyword match, but semantically relevant. |

---

### Step 1: Find Min and Max values

To normalise the scores, we identify the absolute minimum and maximum raw values present in our candidate pool:

*   **Vector Bounds:**
    *   $\text{Max}_{\text{vector}} = 0.85$
    *   $\text{Min}_{\text{vector}} = 0.60$
    *   $\text{Range}_{\text{vector}} = 0.85 - 0.60 = 0.25$

*   **BM25 Bounds:**
    *   $\text{Max}_{\text{bm25}} = 6.0$
    *   $\text{Min}_{\text{bm25}} = 0.0$
    *   $\text{Range}_{\text{bm25}} = 6.0 - 0.0 = 6.0$

---

### Step 2: Apply Min-Max Normalisation

The formula to scale a raw score $S_{\text{raw}}$ to a normalized score $S_{\text{norm}}$ is:

$$S_{\text{norm}} = \frac{S_{\text{raw}} - \text{Min}}{\text{Max} - \text{Min}}$$

#### Document A
*   **Normalized Vector:**  
    $$\frac{0.85 - 0.60}{0.25} = \frac{0.25}{0.25} = 1.00 \implies \mathbf{100.0\%}$$
*   **Normalized BM25:**  
    $$\frac{6.0 - 0.0}{6.0} = \frac{6.0}{6.0} = 1.00 \implies \mathbf{100.0\%}$$

#### Document B
*   **Normalized Vector:**  
    $$\frac{0.70 - 0.60}{0.25} = \frac{0.10}{0.25} = 0.40 \implies \mathbf{40.0\%}$$
*   **Normalized BM25:**  
    $$\frac{2.0 - 0.0}{6.0} = \frac{2.0}{6.0} = 0.333 \implies \mathbf{33.3\%}$$

#### Document C
*   **Normalized Vector:**  
    $$\frac{0.60 - 0.60}{0.25} = \frac{0.00}{0.25} = 0.00 \implies \mathbf{0.0\%}$$
*   **Normalized BM25:**  
    $$\frac{0.0 - 0.0}{6.0} = \frac{0.0}{6.0} = 0.00 \implies \mathbf{0.0\%}$$

---

### Step 3: Compute Weighted Blending

We blend the normalised scores using the parameter $\alpha$ (alpha) which controls the influence of each search style:

$$\text{Combined Score} = (\alpha \times S_{\text{vector\_norm}}) + ((1 - \alpha) \times S_{\text{bm25\_norm}})$$

*If we set $\alpha = 0.5$ (equal 50/50 split):*

*   **Doc A:**  
    $$(0.5 \times 100.0\%) + (0.5 \times 100.0\%) = \mathbf{100.0\%}$$
*   **Doc B:**  
    $$(0.5 \times 40.0\%) + (0.5 \times 33.3\%) = 20.0\% + 16.65\% = \mathbf{36.65\%}$$
*   **Doc C:**  
    $$(0.5 \times 0.0\%) + (0.5 \times 0.0\%) = \mathbf{0.0\%}$$

---

### Summary Table

| Document | Normalized Vector | Normalized BM25 | Blended Score ($\alpha=0.5$) | Final Rank |
| :--- | :---: | :---: | :---: | :---: |
| **Doc A** | `100.0%` | `100.0%` | **`100.0%`** | **1** |
| **Doc B** | `40.0%` | `33.3%` | **`36.7%`** | **2** |
| **Doc C** | `0.0%` | `0.0%` | **`0.0%`** | **3** |
