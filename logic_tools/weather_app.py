import requests
from datetime import datetime

def fetch_weather_data():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": 24.3740,
        "longitude": 88.6011,
        "current": ["temperature_2m", "relative_humidity_2m", "precipitation_probability", "wind_speed_10m", "wind_direction_10m"],
        "hourly": ["precipitation_probability", "temperature_2m"],
        "forecast_hours": 6,
        "timezone": "auto"
    }

    response = requests.get(url, params=params)
    data = response.json()

    current = data["current"]
    units = data["current_units"]
    hourly = data["hourly"]
    hourly_units = data["hourly_units"]

    summary = (
        f"--- Weather Summary for Rajshahi ---\n"
        f"Temperature: {current['temperature_2m']}{units['temperature_2m']}\n"
        f"Humidity: {current['relative_humidity_2m']}{units['relative_humidity_2m']}\n"
        f"Precipitation Probability (Now): {current['precipitation_probability']}{units['precipitation_probability']}\n"
        f"Wind Speed: {current['wind_speed_10m']}{units['wind_speed_10m']}\n"
        f"Wind Direction: {current['wind_direction_10m']}{units['wind_direction_10m']}\n\n"
        f"--- Hourly Forecast (Next 6h) ---\n"
    )

    times = hourly["time"]
    probs = hourly["precipitation_probability"]
    temps = hourly["temperature_2m"]

    for t, p, temp in zip(times, probs, temps):
        hour = datetime.fromisoformat(t).strftime("%I:%M %p")
        summary += f"{hour}: {temp}{hourly_units['temperature_2m']} | Rain: {p}{hourly_units['precipitation_probability']}\n"

    print(summary)

def main():
    fetch_weather_data()

if __name__ == "__main__":
    main()
