# # 
import pandas as pd

df1 = pd.read_csv("./files/energy/input/load_emulator/results_emulator/mean_profile_load_emulator_v2_300_1.csv", index_col=0, sep=',', decimal='.')
df2 = pd.read_csv("./files/energy/input/load_emulator/results_emulator/mean_profile_load_emulator_v2_300_2.csv", index_col=0, sep=',', decimal='.')
df3 = pd.read_csv("./files/energy/input/load_emulator/results_emulator/mean_profile_load_emulator_v2_300_3.csv", index_col=0, sep=',', decimal='.')


# media dei due profili
mean_profile = (df1 + df2+ df3) / 3

mean_profile.to_csv("media.csv")


import pandas as pd

df = pd.read_csv("media.csv", index_col=0, sep=',', decimal='.')

# trasformare quarto orario in orario (somma per conservare l'energia totale)
df.index = pd.to_datetime(df.index, format='%Y-%m-%d %H:%M:%S')
df_hourly = df.resample('h').sum()
df_hourly.index = range(1, len(df_hourly) + 1)

print(f"Totale quarto-orario: {df.sum().sum():.2f}")
print(f"Totale orario:        {df_hourly.sum().sum():.2f}")

import plotly.graph_objects as go

fig = go.Figure()
fig.add_trace(go.Scatter(x=df_hourly.index, y=df_hourly.iloc[:, 0], mode='lines', name='Mean hourly load'))
fig.update_layout(title='Mean Hourly Load Profile', xaxis_title='Hour of the year', yaxis_title='Energy [kWh]')
fig.show()

df_hourly.to_csv("media_oraria_load_profile.csv")


