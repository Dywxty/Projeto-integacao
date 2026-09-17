#https://open-meteo.com/en/docs?hourly=temperature_2m,visibility,precipitation,wind_speed_80m,soil_moisture_3_to_9cm,wind_direction_10m,apparent_temperature&timezone=America%2FSao_Paulo&daily=sunrise,sunset,moonrise,moonset,temperature_2m_max,temperature_2m_min&current=temperature_2m,is_day,relative_humidity_2m,apparent_temperature,wind_speed_10m,wind_direction_10m,precipitation,rain,showers,snowfall,weather_code#api_response

import openmeteo_requests

import pandas as pd
import requests_cache
from retry_requests import retry

# Setup the Open-Meteo API client with cache and retry on error
cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
openmeteo = openmeteo_requests.Client(session = retry_session)

# Make sure all required weather variables are listed here
# The order of variables in hourly or daily is important to assign them correctly below
url = "https://api.open-meteo.com/v1/forecast"
params = {
	"latitude": 52.52,
	"longitude": 13.41,
	"daily": ["sunrise", "sunset", "moonrise", "moonset", "temperature_2m_max", "temperature_2m_min"],
	"hourly": ["temperature_2m", "visibility", "precipitation", "wind_speed_80m", "soil_moisture_3_to_9cm", "wind_direction_10m", "apparent_temperature"],
	"current": ["temperature_2m", "is_day", "relative_humidity_2m", "apparent_temperature", "wind_speed_10m", "wind_direction_10m", "precipitation", "rain", "showers", "snowfall", "weather_code"],
	"timezone": "America/Sao_Paulo",
}
responses = openmeteo.weather_api(url, params = params)

# Days without a moonrise or moonset return this value instead of a timestamp
missing_int64 = 9223372036854775807

# Process first location. Add a for-loop for multiple locations or weather models
response = responses[0]
print(f"Coordinates: {response.Latitude()}°N {response.Longitude()}°E")
print(f"Elevation: {response.Elevation()} m asl")
print(f"Timezone: {response.Timezone()}{response.TimezoneAbbreviation()}")
print(f"Timezone difference to GMT+0: {response.UtcOffsetSeconds()}s")

# Process current data. The order of variables needs to be the same as requested.
current = response.Current()
current_temperature_2m = current.Variables(0).Value()
current_is_day = current.Variables(1).Value()
current_relative_humidity_2m = current.Variables(2).Value()
current_apparent_temperature = current.Variables(3).Value()
current_wind_speed_10m = current.Variables(4).Value()
current_wind_direction_10m = current.Variables(5).Value()
current_precipitation = current.Variables(6).Value()
current_rain = current.Variables(7).Value()
current_showers = current.Variables(8).Value()
current_snowfall = current.Variables(9).Value()
current_weather_code = current.Variables(10).Value()

print(f"\nCurrent time: {current.Time()}")
print(f"Current temperature_2m: {current_temperature_2m}")
print(f"Current is_day: {current_is_day}")
print(f"Current relative_humidity_2m: {current_relative_humidity_2m}")
print(f"Current apparent_temperature: {current_apparent_temperature}")
print(f"Current wind_speed_10m: {current_wind_speed_10m}")
print(f"Current wind_direction_10m: {current_wind_direction_10m}")
print(f"Current precipitation: {current_precipitation}")
print(f"Current rain: {current_rain}")
print(f"Current showers: {current_showers}")
print(f"Current snowfall: {current_snowfall}")
print(f"Current weather_code: {current_weather_code}")

# Process hourly data. The order of variables needs to be the same as requested.
hourly = response.Hourly()
hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()
hourly_visibility = hourly.Variables(1).ValuesAsNumpy()
hourly_precipitation = hourly.Variables(2).ValuesAsNumpy()
hourly_wind_speed_80m = hourly.Variables(3).ValuesAsNumpy()
hourly_soil_moisture_3_to_9cm = hourly.Variables(4).ValuesAsNumpy()
hourly_wind_direction_10m = hourly.Variables(5).ValuesAsNumpy()
hourly_apparent_temperature = hourly.Variables(6).ValuesAsNumpy()

hourly_data = {
	"date": pd.date_range(
		start = pd.to_datetime(hourly.Time(), unit = "s", utc = True),
		end =  pd.to_datetime(hourly.TimeEnd(), unit = "s", utc = True),
		freq = pd.Timedelta(seconds = hourly.Interval()),
		inclusive = "left"
	).tz_convert(response.Timezone().decode())
}

hourly_data["temperature_2m"] = hourly_temperature_2m
hourly_data["visibility"] = hourly_visibility
hourly_data["precipitation"] = hourly_precipitation
hourly_data["wind_speed_80m"] = hourly_wind_speed_80m
hourly_data["soil_moisture_3_to_9cm"] = hourly_soil_moisture_3_to_9cm
hourly_data["wind_direction_10m"] = hourly_wind_direction_10m
hourly_data["apparent_temperature"] = hourly_apparent_temperature

hourly_dataframe = pd.DataFrame(data = hourly_data)
print("\nHourly data\n", hourly_dataframe)

# Process daily data. The order of variables needs to be the same as requested.
daily = response.Daily()
daily_sunrise = daily.Variables(0).ValuesInt64AsNumpy()
daily_sunset = daily.Variables(1).ValuesInt64AsNumpy()
daily_moonrise = daily.Variables(2).ValuesInt64AsNumpy()
daily_moonset = daily.Variables(3).ValuesInt64AsNumpy()
daily_temperature_2m_max = daily.Variables(4).ValuesAsNumpy()
daily_temperature_2m_min = daily.Variables(5).ValuesAsNumpy()

daily_data = {
	"date": pd.date_range(
		start = pd.to_datetime(daily.Time(), unit = "s", utc = True),
		end =  pd.to_datetime(daily.TimeEnd(), unit = "s", utc = True),
		freq = pd.Timedelta(seconds = daily.Interval()),
		inclusive = "left"
	).tz_convert(response.Timezone().decode())
}

daily_data["sunrise"] = pd.to_datetime(daily_sunrise, unit = "s", utc = True).tz_convert(response.Timezone().decode())
daily_data["sunset"] = pd.to_datetime(daily_sunset, unit = "s", utc = True).tz_convert(response.Timezone().decode())
daily_moonrise = pd.Series(daily_moonrise).mask(daily_moonrise == missing_int64)
daily_data["moonrise"] = pd.to_datetime(daily_moonrise, unit = "s", utc = True).dt.tz_convert(response.Timezone().decode())
daily_moonset = pd.Series(daily_moonset).mask(daily_moonset == missing_int64)
daily_data["moonset"] = pd.to_datetime(daily_moonset, unit = "s", utc = True).dt.tz_convert(response.Timezone().decode())
daily_data["temperature_2m_max"] = daily_temperature_2m_max
daily_data["temperature_2m_min"] = daily_temperature_2m_min

daily_dataframe = pd.DataFrame(data = daily_data)
print("\nDaily data\n", daily_dataframe)
