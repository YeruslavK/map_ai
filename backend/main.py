from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import os
import json
import re
import logging
import requests
from typing import List, Dict, Any
import time
import io

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)
logger.info(f"OpenAI API Key available: {client.api_key is not None}")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TripRequest(BaseModel):
    destination: str
    duration: int
    holiday_type: str
    food_preferences: list[str]
    landmarks: str
    activity_level: str

def geocode_location(location_name: str, city: str) -> Dict[str, float]:
    """
    Get coordinates for a location using OpenStreetMap's Nominatim service.
    """
    time.sleep(1)
    
    query = f"{location_name}, {city}"
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={query}"
    
    try:
        response = requests.get(url, headers={'User-Agent': 'MapAI/1.0'})
        response.raise_for_status()
        data = response.json()
        
        if not data:
            logger.warning(f"No results found for location: {query}")
            return None
            
        result = data[0]
        lat = float(result['lat'])
        lon = float(result['lon'])
        
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            logger.error(f"Invalid coordinates received for {query}: lat={lat}, lon={lon}")
            return None
            
        return {
            'latitude': lat,
            'longitude': lon
        }
    except Exception as e:
        logger.error(f"Geocoding error for {query}: {str(e)}")
        return None

def build_prompt(data):

    doubled_duration = data.duration * 2
    return f"""
Your task is to return a **JSON array** of **real, well-known, and currently popular** places that match the user's preferences. Each place must include:

- `name`: string (the official name of the place)
- `type`: string with an emoji, such as:
  - "🏛️ Landmark"
  - "🌳 Park"
  - "🍽️ Food"
  - "🍵 Cafe"
  - "🍺 Bar"
  - "🕺 Dance Club"
  - "🎶 Live Music"
  - "🎭 Show"
  - "🏖️ Beach"
  - "⛷️ Adventure"
  - "🏰 Castle"
  - "🛀 Spa"
- `address`: string (the full address of the place)

👉 Only include **real locations** with **accurate addresses**. Avoid fictional or generic entries.

For a `{doubled_duration}`-day trip to **{doubled_duration}**, return the following:

- **Landmarks**: `{doubled_duration}` places (must include any from: `{data.landmarks}`)
- **Food/Restaurants**: `{doubled_duration}` places (prioritize based on: `{', '.join(data.food_preferences)}`)
- **Activities**: `{doubled_duration}` places (must match activity level: `{data.activity_level}` — e.g., "high" = sports, clubs, hiking; "low" = light walking, galleries)
- **Relaxation spots**: `{doubled_duration}` places (include if holiday type is **relaxation** — e.g., gardens, spas, scenic lounges)
- **Cultural sites**: `{doubled_duration}` places (include if holiday type is **culture** — e.g., museums, theaters, cathedrals)
- **Adventure activities**: `{doubled_duration}` places (include if holiday type is **adventure** — e.g., zip-lining, hiking routes, water sports)
- **Fun/Nightlife spots**: `{doubled_duration}` places (include if activity level is **medium or high**, or if holiday type includes **fun, party, or social** vibes — e.g., bars, live music venues, dance clubs)

Make sure to choose a **variety of places across neighborhoods**, and prioritize places that are **highly rated, currently open**, and **popular with both locals and tourists**.

⚠️ Return **ONLY** the JSON array. Do not include any explanation or extra text.

"""

def extract_json_from_response(response):
    try:
        text = response.choices[0].message.content
        logger.info(f"Raw OpenAI response text: {text}")

        if not text.strip().startswith('['):
            json_match = re.search(r'\[.*\]', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)
            else:
                logger.error("No JSON array found in response")
                raise ValueError("Response does not contain a valid JSON array")

        parsed_json = json.loads(text)
        if not isinstance(parsed_json, list):
            raise ValueError("Response is not a JSON array")
        
        for item in parsed_json:
            if not all(key in item for key in ['name', 'type', 'address']):
                raise ValueError("One or more items missing required fields")
        
        return parsed_json
    except json.JSONDecodeError as e:
        error_message = f"JSON parsing error: {str(e)}, Raw Response: {text if 'text' in locals() else 'No response'}"
        logger.error(error_message)
        raise HTTPException(status_code=500, detail=error_message)
    except Exception as e:
        error_message = f"Failed to parse response: {str(e)}, Raw Response: {text if 'text' in locals() else 'No response'}"
        logger.error(error_message)
        raise HTTPException(status_code=500, detail=error_message)

@app.post('/generate-trip')
async def generate_trip(data: TripRequest):
    try:
        logger.info(f"Received request data: {data}")
        
        if not data.destination:
            raise HTTPException(status_code=400, detail="Destination is required")
        
        prompt = build_prompt(data)
        logger.info(f"Generated Prompt: {prompt}")

        if not client.api_key:
            raise HTTPException(status_code=500, detail="OpenAI API key is not configured")

        logger.info("Calling OpenAI API...")
        try:
            response = client.chat.completions.create(
                model="ft:gpt-3.5-turbo-0125:personal::BWiQfF7y",
                messages=[
                    {"role": "system", "content": "You are a travel assistant AI that generates accurate travel locations for a map. Always return a valid JSON array."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2000
            )
            logger.info("OpenAI API call successful")
        except Exception as api_error:
            logger.error(f"OpenAI API call failed: {str(api_error)}")
            raise HTTPException(status_code=500, detail=f"OpenAI API call failed: {str(api_error)}")

        places = extract_json_from_response(response)
        
        valid_places = []
        for place in places:
            try:
                coords = geocode_location(place['name'], data.destination)
                if coords:
                    place['latitude'] = coords['latitude']
                    place['longitude'] = coords['longitude']
                    valid_places.append(place)
                    logger.info(f"Successfully geocoded {place['name']} to coordinates {coords}")
                else:
                    logger.warning(f"Could not geocode location: {place['name']} in {data.destination}")
            except Exception as e:
                logger.error(f"Error processing location {place['name']}: {str(e)}")
        
        if not valid_places:
            raise HTTPException(
                status_code=404,
                detail="No valid locations could be found with coordinates. Please try a different destination or modify your preferences."
            )
        
        logger.info(f"Successfully processed {len(valid_places)} locations")
        return valid_places
    except HTTPException:
        raise
    except Exception as e:
        error_detail = f"Error in generate_trip: {str(e)}"
        logger.error(error_detail, exc_info=True)
        raise HTTPException(status_code=500, detail=error_detail)

def get_icon_for_type(place_type: str) -> tuple[str, str]:
    """Get the appropriate icon and color for a place type."""
    # Extract the type from the string (e.g., "🍽️ Food" -> "Food")
    type_name = place_type.split(" ", 1)[1] if " " in place_type else place_type
    logger.info(f"Processing type: '{place_type}' -> extracted type: '{type_name}'")
    
    # Define icon and color mappings using Google Maps' built-in icons
    icon_mappings = {
        "Landmark": ("http://maps.google.com/mapfiles/kml/shapes/schools.png", "#FF0000"),  
        "Park": ("http://maps.google.com/mapfiles/kml/shapes/parks.png", "#00FF00"), 
        "Food": ("http://maps.google.com/mapfiles/kml/pal2/icon42.png", "#FFA500"),  
        "Cafe": ("http://maps.google.com/mapfiles/kml/shapes/coffee.png", "#FFA500"),  
        "Bar": ("http://maps.google.com/mapfiles/kml/shapes/bars.png", "#FFA500"),  
        "Dance Club": ("http://maps.google.com/mapfiles/kml/shapes/bar.png", "#FF00FF"),  
        "Live Music": ("http://maps.google.com/mapfiles/kml/shapes/arts.png", "#FF00FF"),  
        "Show": ("http://maps.google.com/mapfiles/kml/shapes/arts.png", "#FF00FF"), 
        "Beach": ("http://maps.google.com/mapfiles/kml/shapes/swimming.png", "#00FFFF"), 
        "Adventure": ("http://maps.google.com/mapfiles/kml/shapes/hiker.png", "#0000FF"),  
        "Castle": ("http://maps.google.com/mapfiles/kml/shapes/landmark.png", "#800080"),  
        "Spa": ("http://maps.google.com/mapfiles/kml/shapes/health.png", "#FF69B4"),  
    }
    
    # Default icon and color if type not found
    default_icon = "http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png"
    default_color = "#000000"  
    
    # Find the best matching icon (case-insensitive)
    for key, (icon, color) in icon_mappings.items():
        if key.lower() == type_name.lower():
            logger.info(f"Matched type '{type_name}' with icon '{key}'")
            return icon, color
    
    logger.warning(f"No matching icon found for type '{type_name}', using default icon")
    return default_icon, default_color

def json_to_kml(places: List[Dict[str, Any]]) -> str:
    """Convert the places JSON to KML format with custom icons."""
    logger.info("Converting places to KML format")
    for place in places:
        logger.info(f"Place type: {place.get('type', 'unknown')}")
    
    kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
    <name>Travel Itinerary</name>
    <description>Generated travel locations</description>
"""
    
    # Add custom styles for each unique type
    used_styles = {}
    for place in places:
        type_name = place['type'].split(" ", 1)[1] if " " in place['type'] else place['type']
        if type_name not in used_styles:
            icon_url, color = get_icon_for_type(place['type'])
            style_id = f"style_{type_name.lower()}"
            kml += f"""
    <Style id="{style_id}">
        <IconStyle>
            <color>{color}</color>
            <scale>1.0</scale>
            <Icon>
                <href>{icon_url}</href>
            </Icon>
            <hotSpot x="0.5" y="0.5" xunits="fraction" yunits="fraction"/>
        </IconStyle>
        <BalloonStyle>
            <text><![CDATA[
                <h3>$[name]</h3>
                <p><b>Type:</b> $[type]</p>
                <p><b>Address:</b> $[address]</p>
            ]]></text>
        </BalloonStyle>
    </Style>
"""
            used_styles[type_name] = style_id
    
    # Add placemarks with their respective styles
    for place in places:
        type_name = place['type'].split(" ", 1)[1] if " " in place['type'] else place['type']
        style_id = used_styles[type_name]
        
        kml += f"""
    <Placemark>
        <name>{place['name']}</name>
        <description>
            <![CDATA[
            <b>Type:</b> {place['type']}<br>
            <b>Address:</b> {place['address']}<br>
            ]]>
        </description>
        <styleUrl>#{style_id}</styleUrl>
        <Point>
            <coordinates>{place['longitude']},{place['latitude']},0</coordinates>
        </Point>
    </Placemark>
"""
    
    kml += """
</Document>
</kml>"""
    return kml

@app.post('/download-kml')
async def download_kml(places: List[Dict[str, Any]]):
    """Convert places to KML and return as downloadable file."""
    try:
        if not places:
            raise HTTPException(status_code=400, detail="No places data provided")
            
        kml_content = json_to_kml(places)
        
        
        kml_file = io.BytesIO(kml_content.encode('utf-8'))
        
        
        return StreamingResponse(
            kml_file,
            media_type="application/vnd.google-earth.kml+xml",
            headers={
                "Content-Disposition": "attachment; filename=travel_itinerary.kml"
            }
        )
    except Exception as e:
        logger.error(f"Error creating KML file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating KML file: {str(e)}")

# Add a simple health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api-key-status")
async def api_key_status():
    """Check if the API key is available (don't return the actual key)"""
    key = os.environ.get("OPENAI_API_KEY")
    return {"status": "available" if key else "missing"}

# Add more detailed error logging
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logger.error(f"HTTP error occurred: {exc.detail}")
    return {"detail": str(exc.detail)}

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unexpected error occurred: {str(exc)}", exc_info=True)
    return {"detail": "Internal server error occurred"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)