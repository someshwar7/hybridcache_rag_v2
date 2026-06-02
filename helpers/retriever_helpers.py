from typing import Dict, Any

def align_result_attributes(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Standardizes result dictionaries to ensure that RAG, direct LLM,
    and web scraping responses share the exact same attributes/keys
    for uniform display and validation.
    """
    # Resolve overall accuracy score
    overall_accuracy = item.get("overall_accuracy") or item.get("score_pct")
    if overall_accuracy is None:
        sim_val = item.get("similarity")
        if sim_val is not None and float(sim_val) > 0.0:
            overall_accuracy = float(sim_val) * 100.0
        else:
            overall_accuracy = 0.0

    bm25_raw = item.get("bm25_raw")
    vector_raw = item.get("vector_raw")
    bm25_norm = item.get("bm25_norm")
    vector_norm = item.get("vector_norm")
    score_pct = item.get("score_pct")

    measures = None
    if any(x is not None for x in [bm25_raw, vector_raw, bm25_norm, vector_norm, score_pct]):
        measures = {
            "bm25_raw":    float(bm25_raw) if bm25_raw is not None else None,
            "vector_raw":  float(vector_raw) if vector_raw is not None else None,
            "bm25_norm":   float(bm25_norm) if bm25_norm is not None else None,
            "vector_norm": float(vector_norm) if vector_norm is not None else None,
            "score_pct":   float(score_pct) if score_pct is not None else None,
        }

    # Resolve confidence label for user display
    accuracy_val = round(float(overall_accuracy), 2)
    confidence_label = "Low"
    if accuracy_val >= 85.0:
        confidence_label = "High"
    elif accuracy_val >= 50.0:
        confidence_label = "Medium"

    accuracy = {
        "overall_accuracy": accuracy_val,
        "confidence_label": confidence_label
    }

    return {
        "chunk_text":          str(item.get("chunk_text", "")),
        "page_no":             int(item.get("page_no", 0)),
        "header":              str(item.get("header") or ""),
        "document_title":      str(item.get("document_title") or item.get("filename") or "Unknown Document"),
        "document_id":         int(item.get("document_id", 0)),
        "source":              str(item.get("source") or item.get("source_file") or ""),
        "overall_accuracy":    accuracy_val,
        "similarity":          round(float(item.get("similarity", 0.0)), 4),
        "rank":                int(item.get("rank", 1)),
        "has_tables":          bool(item.get("has_tables", False)),
        "has_images":          bool(item.get("has_images", False)),
        "key_takeaways":       list(item.get("key_takeaways") or []),
        "suggested_followups": list(item.get("suggested_followups") or []),
        "measures":            measures,
        "accuracy":            accuracy
    }
