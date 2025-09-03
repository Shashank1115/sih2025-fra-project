import folium

def generate_claim_map(lat, lon, patta_holder, village, claim_status, output_path="sample_data/claim_location_map.html"):
    m = folium.Map(location=[lat, lon], zoom_start=14)

    popup_text = (
        f"Patta Holder: {patta_holder}<br>"
        f"Village: {village}<br>"
        f"Status: {claim_status}"
    )

    folium.Marker(
        [lat, lon],
        popup=popup_text,
        tooltip="Claim Location"
    ).add_to(m)

    m.save(output_path)
    return output_path
