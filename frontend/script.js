document.addEventListener("DOMContentLoaded", () => {
  const map = L.map("map").setView([41.89024611192267, 12.492338185100092], 14);

  const mainLayer = L.tileLayer(
    "https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}.png",
    {
      minZoom: 3,
      maxZoom: 18,
      attribution:
        '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a>, &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }
  );
  mainLayer.addTo(map);

  const marker = L.marker([41.89024611192267, 12.492338185100092]).addTo(map);
  marker.bindPopup("<b>Welcome!</b><br>Your trip starts here.").openPopup();

  // Handle form submit
  document.getElementById("map-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const submitButton = e.target.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    submitButton.textContent = "Generating...";

    try {
      const { status, baseUrl } = await checkBackendHealth();
      if (!status || !baseUrl) {
        throw new Error("Backend server is not reachable.");
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

      const response = await fetch(`${baseUrl}/generate-trip`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        mode: "cors",
        body: JSON.stringify(tripData),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to generate trip");
      }

      const pinpoints = await response.json();
      console.log("Generated Pinpoints:", pinpoints);

      if (!pinpoints || pinpoints.length === 0) {
        throw new Error(
          "No valid locations found. Please try a different destination or modify your preferences."
        );
      }

      // Clear existing markers
      map.eachLayer((layer) => {
        if (layer instanceof L.Marker) {
          map.removeLayer(layer);
        }
      });

      // Add markers to map
      pinpoints.forEach((place) => {
        if (!place.latitude || !place.longitude) {
          console.warn(`Skipping invalid coordinates for ${place.name}`);
          return;
        }

        const emoji = extractEmoji(place.type);

        const customIcon = L.divIcon({
          className: "custom-div-icon",
          html: `<div class="emoji-marker">${emoji}</div>`,
          iconSize: [30, 30],
          iconAnchor: [15, 30],
          popupAnchor: [0, -30],
        });

        L.marker([place.latitude, place.longitude], { icon: customIcon })
          .addTo(map)
          .bindPopup(
            `<b>${place.name}</b><br>Type: ${place.type}<br>Address: ${
              place.address || "N/A"
            }`
          );
      });

      // Fit map to show all markers
      const bounds = L.latLngBounds(
        pinpoints.map((p) => [p.latitude, p.longitude])
      );
      map.fitBounds(bounds);
    } catch (error) {
      console.error("Error:", error);
      if (error.message.includes("not reachable")) {
        alert(
          "Cannot connect to the server. Please ensure the backend server is running."
        );
      } else if (
        error.name === "TypeError" &&
        error.message.includes("Failed to fetch")
      ) {
        alert("Network error: Cannot connect to the server.");
      } else {
        alert("Error generating trip: " + error.message);
      }
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Generate Map";
    }
  });

  // Toggle selection
  document.querySelectorAll(".food-prefrences").forEach((option) => {
    option.addEventListener("click", () => {
      option.classList.toggle("selected");
    });
  });
});

// Extract emoji from type string
function extractEmoji(type) {
  return type.split(" ")[0];
}

// Backend health check
async function checkBackendHealth() {
  try {
    const endpoints = [
      "http://localhost:8001/health",
      "http://127.0.0.1:8001/health",
    ];

    for (const endpoint of endpoints) {
      try {
        const response = await fetch(endpoint);
        if (response.ok) {
          return { status: true, baseUrl: endpoint.replace("/health", "") };
        }
      } catch (error) {
        console.log(`Failed to connect to ${endpoint}`);
      }
    }
    return { status: false, baseUrl: null };
  } catch (error) {
    return { status: false, baseUrl: null };
  }
}
