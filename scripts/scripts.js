// scripts/scripts.js
document.addEventListener("DOMContentLoaded", function () {
  console.log("DOM Loaded");

  // Rechercher la variable 'map' créée par Folium (elle est généralement nommée map_1, map_2, etc.)
  var map;
  for (var key in window) {
    if (key.startsWith("map_") && window[key] instanceof L.Map) {
      map = window[key];
      break;
    }
  }
  if (!map) {
    console.error("Map not found");
    return;
  }

  // Récupérer les données des itinéraires injectées par Python
  var livreursData = window.livreursData || {};
  // Normaliser les IDs pour être de la forme "L1", "L2", etc.
  Object.keys(livreursData).forEach(function (key) {
    if (!key.startsWith("L")) {
      livreursData["L" + key] = livreursData[key];
      delete livreursData[key];
    }
  });

  var markers = {}; // Stocke les marqueurs par véhicule
  var animationSpeed = 500; // Intervalle (ms) entre chaque incrément du slider

  // Création d'un marqueur pour chaque véhicule
  for (var liv_id in livreursData) {
    var data = livreursData[liv_id];
    if (data.points.length > 0) {
      var firstPoint = data.points[0];
      var marker = L.marker([firstPoint.lat, firstPoint.lon], {
        icon: L.AwesomeMarkers.icon({
          icon: "truck",
          markerColor: data.color,
          prefix: "fa",
        }),
      }).addTo(map);
      marker.bindPopup("<b>Livreur " + liv_id + "</b>");
      markers[liv_id] = marker;
    }
  }

  // Configuration du slider
  var slider = document.getElementById("timeSlider");
  var timeLabel = document.getElementById("timeLabel");

  // Déterminer le temps global (en ms) à partir des premiers et derniers points
  var globalMinTime = null,
    globalMaxTime = null;
  for (var liv_id in livreursData) {
    var pts = livreursData[liv_id].points;
    if (pts.length > 0) {
      var first = new Date(pts[0].time).getTime();
      var last = new Date(pts[pts.length - 1].time).getTime();
      if (globalMinTime === null || first < globalMinTime)
        globalMinTime = first;
      if (globalMaxTime === null || last > globalMaxTime) globalMaxTime = last;
    }
  }
  var totalSec = Math.floor((globalMaxTime - globalMinTime) / 1000);
  slider.min = 0;
  slider.max = totalSec;
  slider.value = 0;

  function updateMap() {
    var deltaSec = parseInt(slider.value);
    var currentTime = globalMinTime + deltaSec * 1000;
    var currentDate = new Date(currentTime);
    timeLabel.innerHTML = "Heure: " + currentDate.toLocaleTimeString();

    // Pour chaque véhicule, déterminer la position correspondant au temps actuel
    for (var liv_id in livreursData) {
      var pts = livreursData[liv_id].points;
      if (pts.length === 0) continue;
      var bestPoint = pts[0];
      for (var i = 0; i < pts.length; i++) {
        var ptTime = new Date(pts[i].time).getTime();
        if (ptTime <= currentTime) {
          bestPoint = pts[i];
        } else {
          break;
        }
      }
      if (markers[liv_id]) {
        markers[liv_id].setLatLng([bestPoint.lat, bestPoint.lon]);
        markers[liv_id].setPopupContent(
          "<b>Livreur " + liv_id + "</b><br>Node: " + bestPoint.node
        );
      }
    }
  }

  slider.addEventListener("input", updateMap);

  var playing = false;
  var intervalID = null;
  var playButton = document.getElementById("playButton");
  var speedUpButton = document.getElementById("speedUpButton");
  var slowDownButton = document.getElementById("slowDownButton");

  playButton.addEventListener("click", function () {
    if (!playing) {
      playing = true;
      playButton.innerHTML = "Pause";
      intervalID = setInterval(function () {
        var curVal = parseInt(slider.value);
        if (curVal < slider.max) {
          slider.value = curVal + 1;
          updateMap();
        } else {
          clearInterval(intervalID);
          playing = false;
          playButton.innerHTML = "Play";
        }
      }, animationSpeed);
    } else {
      playing = false;
      playButton.innerHTML = "Play";
      clearInterval(intervalID);
    }
  });

  speedUpButton.addEventListener("click", function () {
    if (animationSpeed > 100) {
      animationSpeed -= 100;
      if (playing) {
        clearInterval(intervalID);
        intervalID = setInterval(function () {
          var curVal = parseInt(slider.value);
          if (curVal < slider.max) {
            slider.value = curVal + 1;
            updateMap();
          } else {
            clearInterval(intervalID);
            playing = false;
            playButton.innerHTML = "Play";
          }
        }, animationSpeed);
      }
    }
  });

  slowDownButton.addEventListener("click", function () {
    animationSpeed += 100;
    if (playing) {
      clearInterval(intervalID);
      intervalID = setInterval(function () {
        var curVal = parseInt(slider.value);
        if (curVal < slider.max) {
          slider.value = curVal + 1;
          updateMap();
        } else {
          clearInterval(intervalID);
          playing = false;
          playButton.innerHTML = "Play";
        }
      }, animationSpeed);
    }
  });

  updateMap();
});
