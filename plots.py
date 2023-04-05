"""Plot the horniness of the shipping matrix.
"""

import webbrowser

import pandas
import plotnine


n_ships = 20


ships = pandas.read_csv('ships.csv')

ships['counts'] = ships['explicit'].astype(str) + '/' + ships['fics'].astype(str)
ships = ships.dropna()
ships = ships.nlargest(n_ships, ['fics'], keep='all')
ships = ships.sort_values(['p'])
ships['ship'] = pandas.Categorical(
    ships['ship'],
    categories=ships['ship'].tolist()
)

fig = (
    plotnine.ggplot(ships)
    + plotnine.aes(
        x='ship',
        y='fics',
        fill='p',
        label='counts'
    )
    + plotnine.labs(
        x='',
        fill='thirst factor'
    )
    + plotnine.scale_y_continuous(
        expand=(0.05, 0, 0.1, 0)
    )
    + plotnine.scale_fill_continuous(
        cmap_name='Reds',
        limits=(0, ships['p'].max())
    )
    + plotnine.geom_col()
    + plotnine.geom_text()
    + plotnine.coord_flip()
)

fig_filename = 'fig.png'
fig.save(fig_filename)
webbrowser.open(fig_filename)
