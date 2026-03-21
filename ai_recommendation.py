def generate_recommendations(detections, age, gender):
    """
    Generate smart dental recommendations based on:
    - YOLO detected labels + real confidence scores
    - Patient age (child / teen / adult / senior)
    - Patient gender (Male / Female / Other)

    detections: list of {"label": str, "confidence": float}
    age: str or int
    gender: str ("Male" / "Female" / "Other")
    """

    # ── Parse age ──────────────────────────────────────────────
    try:
        age_int = int(age)
    except:
        age_int = 25  # default adult

    if age_int <= 12:
        age_group = "child"
    elif age_int <= 19:
        age_group = "teen"
    elif age_int <= 59:
        age_group = "adult"
    else:
        age_group = "senior"

    gender = (gender or "").strip().lower()

    # ── Summarise detections ───────────────────────────────────
    summary = {}
    for d in detections:
        label = d["label"]
        conf  = d["confidence"]
        if label not in summary:
            summary[label] = {"count": 0, "conf": []}
        summary[label]["count"] += 1
        summary[label]["conf"].append(conf)

    recommendations = []

    # ── Per-condition logic ────────────────────────────────────
    for label, data in summary.items():

        avg_conf = sum(data["conf"]) / len(data["conf"])
        count    = data["count"]

        # ── CARIES ──────────────────────────────────────────
        if label == "caries":

            if age_group == "child":
                if count >= 2 or avg_conf >= 0.7:
                    rec = (
                        "Multiple carious lesions detected in a child. "
                        "Immediate pediatric dental consultation required. "
                        "Fluoride treatment, tooth-colored fillings, and dietary sugar reduction are strongly advised."
                    )
                else:
                    rec = (
                        "Early childhood caries detected. "
                        "Fluoride application and dental sealants are recommended. "
                        "Limit sugary foods and establish brushing habits twice daily."
                    )

            elif age_group == "teen":
                if count >= 2 or avg_conf >= 0.7:
                    rec = (
                        "Significant caries detected in a teenager. "
                        "Restorative treatment (fillings) is recommended promptly. "
                        "Reduce carbonated drinks and sugary snacks. "
                        "Brush with fluoride toothpaste after every meal."
                    )
                else:
                    rec = (
                        "Early caries detected. Dental sealants and fluoride varnish are advised. "
                        "Maintain regular 6-monthly dental visits."
                    )

            elif age_group == "adult":
                if count >= 2 and avg_conf >= 0.7:
                    rec = (
                        "Multiple high-confidence carious lesions detected. "
                        "Root canal therapy or restorative treatment is strongly recommended. "
                        "Consult a dentist immediately to prevent further decay."
                    )
                elif count >= 2:
                    rec = (
                        "Multiple caries detected. Composite fillings or inlays are recommended. "
                        "Reduce sugar intake and maintain proper flossing habits."
                    )
                else:
                    rec = (
                        "Early-stage caries detected. "
                        "Preventive care (fluoride varnish, dietary changes) and regular monitoring advised."
                    )

            else:  # senior
                if count >= 2 or avg_conf >= 0.65:
                    rec = (
                        "Advanced caries detected in an older patient. "
                        "Root caries are common in seniors — RCT, crown or extraction may be needed. "
                        "Consult your dentist urgently. Use fluoride mouth rinse daily."
                    )
                else:
                    rec = (
                        "Caries detected. Seniors are at higher risk due to dry mouth (xerostomia). "
                        "Restorative treatment and increased fluoride use are recommended."
                    )

            # Female-specific note
            if gender == "female" and age_group in ("adult", "senior"):
                rec += (
                    " Note: Hormonal changes (pregnancy, menopause) can accelerate dental decay "
                    "— increased dental monitoring is advised."
                )

        # ── STAINS ──────────────────────────────────────────
        elif label == "stains":

            if age_group == "child":
                rec = (
                    "Dental staining detected. Common causes include iron supplements or poor brushing. "
                    "Professional cleaning and improved brushing technique are recommended."
                )
            elif age_group == "teen":
                if avg_conf >= 0.65:
                    rec = (
                        "Moderate staining detected. Professional scaling is recommended. "
                        "Avoid tobacco, excessive tea/coffee and fizzy drinks."
                    )
                else:
                    rec = (
                        "Mild staining detected. Improve brushing technique and consider whitening toothpaste."
                    )
            elif age_group == "adult":
                if avg_conf >= 0.65:
                    rec = (
                        "Noticeable dental staining detected. "
                        "Professional scaling and polishing are strongly recommended. "
                        "Teeth whitening treatment may be considered after cleaning."
                    )
                else:
                    rec = (
                        "Mild staining detected. Routine professional cleaning is sufficient. "
                        "Reduce tea, coffee and tobacco use."
                    )
            else:  # senior
                rec = (
                    "Dental staining detected. Professional cleaning is recommended. "
                    "Seniors should be careful with whitening agents — consult your dentist before use."
                )

        # ── MALALIGNED ──────────────────────────────────────
        elif label == "malaligned":

            if age_group == "child":
                rec = (
                    "Tooth misalignment detected at an early age — this is the best time to treat. "
                    "Early orthodontic evaluation is strongly recommended. "
                    "Space maintainers or early braces may be advised."
                )
            elif age_group == "teen":
                rec = (
                    "Tooth misalignment detected. Teenage years are ideal for orthodontic correction. "
                    "Traditional braces or clear aligners (Invisalign) are recommended. "
                    "Consult an orthodontist soon."
                )
            elif age_group == "adult":
                rec = (
                    "Tooth misalignment detected. Adult orthodontic treatment is very effective. "
                    "Clear aligners or ceramic braces are popular discreet options. "
                    "An orthodontic consultation is recommended."
                )
            else:  # senior
                rec = (
                    "Tooth misalignment detected. "
                    "Orthodontic options are available for seniors including clear aligners. "
                    "Consult your dentist to assess suitability based on bone density."
                )

        # ── PIT & FISSURE ────────────────────────────────────
        elif label == "pit_fissure":

            if age_group in ("child", "teen"):
                rec = (
                    "Pit and fissure caries detected — very common in younger patients. "
                    "Dental sealants are highly effective and strongly recommended at this age. "
                    "Schedule a sealant application at your next dental visit."
                )
            elif age_group == "adult":
                if avg_conf >= 0.65:
                    rec = (
                        "Pit and fissure caries with moderate-to-high confidence detected. "
                        "Restorative fillings or composite bonding are recommended. "
                        "Deep cleaning before restoration may be required."
                    )
                else:
                    rec = (
                        "Early pit and fissure decay detected. "
                        "Preventive sealants or minimal restorative treatment are advised."
                    )
            else:  # senior
                rec = (
                    "Pit and fissure caries detected. "
                    "Restorative treatment with fillings or crowns is recommended depending on depth. "
                    "Seniors should schedule bi-annual dental check-ups."
                )

        # ── UNKNOWN ──────────────────────────────────────────
        else:
            rec = (
                f"Dental condition detected (confidence: {avg_conf:.0%}). "
                "A clinical dental consultation is recommended for proper diagnosis and treatment."
            )

        recommendations.append({
            "label":      label,
            "count":      count,
            "confidence": round(avg_conf, 2),
            "age_group":  age_group,
            "gender":     gender,
            "recommendation": rec
        })

    # ── If nothing detected ────────────────────────────────────
    if not recommendations:
        base = "No major oral health issues detected."

        if age_group == "child":
            extra = "Maintain brushing twice daily with fluoride toothpaste. Visit a dentist every 6 months."
        elif age_group == "teen":
            extra = "Keep up good oral hygiene. Avoid sugary drinks. Visit a dentist every 6 months."
        elif age_group == "adult":
            extra = "Continue regular dental check-ups every 6 months and maintain daily flossing."
        else:
            extra = "Seniors should visit a dentist every 4-6 months. Use fluoride mouth rinse daily."

        if gender == "female":
            extra += " Women should inform their dentist about hormonal changes that may affect oral health."

        recommendations.append({
            "label":          "none",
            "count":          0,
            "confidence":     0,
            "age_group":      age_group,
            "gender":         gender,
            "recommendation": f"{base} {extra}"
        })

    return recommendations