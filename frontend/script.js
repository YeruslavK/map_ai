let map;

document.addEventListener("DOMContentLoaded", () => {
  // Initialize the map
  map = L.map("map").setView([41.89024611192267, 12.492338185100092], 1);

  L.tileLayer(
    "https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png",
    {
      maxZoom: 20,
      minZoom: 2,
      attribution:
        '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }
  ).addTo(map);

  // const marker = L.marker([41.89024611192267, 12.492338185100092]).addTo(map);
  // marker.bindPopup("<b>Welcome!</b><br>Your trip starts here.").openPopup();
});

const options = document.querySelectorAll(".food-prefrences");
let currentPinpoints = [];
let markers = [];

options.forEach((option) => {
  option.addEventListener("click", () => {
    option.classList.toggle("selected");
  });
});

async function checkBackendHealth() {
  try {
    const response = await fetch("http://127.0.0.1:8001/health");
    return response.ok;
  } catch (error) {
    return false;
  }
}

function clearMarkers() {
  markers.forEach((marker) => marker.remove());
  markers = [];
}

function addPinpointsToMap(map, pinpoints) {
  clearMarkers();
  currentPinpoints = pinpoints;
  pinpoints.forEach((point) => {
    // Extract emoji from the type (assumes format is "emoji Type")
    const emoji = point.type.split(" ")[0];

    // Create custom icon using the emoji
    const customIcon = L.divIcon({
      html: `<div style="font-size: 24px;">${emoji}</div>`,
      className: "emoji-marker",
      iconSize: [30, 30],
      iconAnchor: [15, 15],
    });

    const marker = L.marker([point.latitude, point.longitude], {
      icon: customIcon,
    })
      .bindPopup(
        `
        <b>${point.name}</b><br>
        Type: ${point.type}<br>
        Address: ${point.address}
      `
      )
      .addTo(map);

    markers.push(marker);
  });

  if (pinpoints.length > 0) {
    const bounds = L.latLngBounds(
      pinpoints.map((p) => [p.latitude, p.longitude])
    );
    map.fitBounds(bounds, { padding: [50, 50] });
  }

  // Enable the download KML button
  const downloadButton = document.getElementById("download-kml");
  downloadButton.disabled = false;
  downloadButton.classList.add("enabled");
}

document.getElementById("map-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const submitButton = e.target.querySelector('button[type="submit"]');
  const downloadButton = document.getElementById("download-kml");
  submitButton.disabled = true;
  submitButton.textContent = "Generating...";
  downloadButton.disabled = true;
  downloadButton.classList.remove("enabled");

  try {
    const isBackendHealthy = await checkBackendHealth();
    if (!isBackendHealthy) {
      throw new Error(
        "Backend server is not reachable. Please ensure the server is running."
      );
    }

    const destination = document.getElementById("destination").value;
    const duration = parseInt(document.getElementById("duration").value);
    const holiday_type = document.getElementById("holiday-type").value;
    const landmarks = document.getElementById("landmark").value;
    const activity_level = document.getElementById("activity-level").value;

    const food_preferences = Array.from(
      document.querySelectorAll(".food-prefrences.selected")
    ).map((el) => el.dataset.value);

    const tripData = {
      destination,
      duration,
      holiday_type,
      food_preferences,
      landmarks,
      activity_level,
    };

    console.log("Sending data:", tripData);

    const response = await fetch("http://127.0.0.1:8001/generate-trip", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(tripData),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || "Failed to generate trip");
    }
    const pinpoints = await response.json();
    console.log("Generated Pinpoints:", pinpoints);

    // Use the existing map instance
    addPinpointsToMap(map, pinpoints);
  } catch (error) {
    console.error("Error:", error);
    if (error.message.includes("not reachable")) {
      alert(
        "Cannot connect to the server. Please ensure the backend server is running at http://127.0.0.1:8001"
      );
    } else if (
      error.name === "TypeError" &&
      error.message.includes("Failed to fetch")
    ) {
      alert(
        "Network error: Cannot connect to the server. Please check if the backend server is running."
      );
    } else {
      alert("Error generating trip: " + error.message);
    }
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Generate Map";
  }
});

// Handle KML download
document.getElementById("download-kml").addEventListener("click", async (e) => {
  // Prevent form submission and event bubbling
  e.preventDefault();
  e.stopPropagation();

  if (!currentPinpoints.length) {
    alert("Please generate a trip first before downloading the KML file.");
    return;
  }

  try {
    const response = await fetch("http://127.0.0.1:8001/download-kml", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(currentPinpoints),
    });

    if (!response.ok) {
      throw new Error("Failed to download KML file.");
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "trip.kml";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error("Download error:", error);
    alert("Error downloading KML file.");
  }
});
