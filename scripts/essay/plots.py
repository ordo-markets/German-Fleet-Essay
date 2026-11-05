"""The essay's four figures, from the published series and the fleet table only (matplotlib).

  fig_a_fleet.png       the 84.2 GW of listed German thermal and hydro capacity, by 2025 status
  fig_b_coal.png        lignite and hard coal: model energy / ENTSO-E A75 energy, before & after
  fig_c_net.png         Germany's cumulative net export through 2025: actual, before, after
  fig_d_setters.png     hours in which each fuel set Germany's price, before & after
Each figure gets a <name>.csv with the numbers it draws (the table under it in the essay).
Palette: the dataviz reference categorical slots, validated (light surface).

    python3 -I scripts/essay/plots.py <series_dir> <fleet_table_out_dir> <out_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt   # noqa: E402
import pandas as pd               # noqa: E402

SURFACE, INK, INK2, MUTED, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#8a8984', '#e4e3df'
SLOT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300']
BEFORE, AFTER = SLOT[1], SLOT[0]
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.edgecolor': GRID,
                     'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2,
                     'figure.facecolor': SURFACE, 'axes.facecolor': SURFACE,
                     'savefig.facecolor': SURFACE})


def frame(ax, grid_axis='y'):
    for s in ('top', 'right', 'left'):
        ax.spines[s].set_visible(False)
    ax.spines['bottom'].set_color(GRID)
    ax.grid(axis=grid_axis, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def title(fig, t, sub):
    fig.text(0.02, 0.97, t, fontsize=13, fontweight='bold', color=INK, va='top')
    fig.text(0.02, 0.905, sub, fontsize=9.5, color=INK2, va='top')


def fig_a(fleet, out):
    t = pd.read_csv(fleet / 'table.csv').set_index('class').mw
    parts = [('In the 2025 market', 'market'), ('Counted twice', 'duplicate'),
             ('Closed before 2025', 'closed_pre_2025'), ('Reserve or closed in 2025', 'out_2025'),
             ('Status unknown', 'unknown_2025'), ('No register row', 'no_register_row')]
    d = pd.DataFrame([(lab, t[k] / 1e3) for lab, k in parts], columns=['category', 'gw'])
    d['share'] = d.gw / d.gw.sum()
    fig, ax = plt.subplots(figsize=(9, 3.4))
    fig.subplots_adjust(left=0.02, right=0.98, top=0.72, bottom=0.30)
    left = 0.0
    for (_, r), c in zip(d.iterrows(), SLOT):
        ax.barh(0, r.gw, left=left, height=0.5, color=c, edgecolor=SURFACE, linewidth=2)
        if r.gw > 6:
            ax.text(left + r.gw / 2, 0, f'{r.gw:.1f}', ha='center', va='center', fontsize=10,
                    color='white' if c in (SLOT[0], SLOT[1], SLOT[5]) else INK, fontweight='bold')
        left += r.gw
    nm = d.gw.iloc[1:4].sum()
    ax.annotate('', xy=(d.gw.iloc[0], 0.42), xytext=(d.gw.iloc[:4].sum(), 0.42),
                arrowprops=dict(arrowstyle='-', color=INK2, lw=1))
    ax.text(d.gw.iloc[0] + nm / 2, 0.48, f'not in the 2025 market: {nm:.1f} GW '
            f'({nm / d.gw.sum():.1%})', ha='center', va='bottom', fontsize=9.5, color=INK)
    ax.set_xlim(0, d.gw.sum())
    ax.set_ylim(-0.4, 0.75)
    ax.axis('off')
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in SLOT]
    ax.legend(handles, [f'{a} ({g:.1f} GW)' for a, g in zip(d.category, d.gw)], ncol=3,
              loc='upper center', bbox_to_anchor=(0.5, -0.02), frameon=False, fontsize=9,
              labelcolor=INK2, handlelength=1, handleheight=1)
    title(fig, 'One inventory of German power plants: 84.2 GW',
          'Listed thermal and hydro capacity, by what the public registers say about 2025 (GW)')
    fig.savefig(out / 'fig_a_fleet.png', dpi=200)
    d.round(3).to_csv(out / 'fig_a_fleet.csv', index=False)


def fig_b(series, out):
    g = pd.concat([pd.read_csv(series / f) for f in ('de_generation_by_family_hourly.csv',
                                                     'de_generation_a75_hourly.csv')],
                  ignore_index=True)
    s = g.groupby('series')[['lignite', 'hard_coal']].sum() / 1e6
    d = pd.DataFrame({'fuel': ['Lignite', 'Hard coal'],
                      'actual_twh': [s.at['actual_a75', 'lignite'], s.at['actual_a75', 'hard_coal']],
                      'before_twh': [s.at['model_before', 'lignite'], s.at['model_before', 'hard_coal']],
                      'after_twh': [s.at['model_after', 'lignite'], s.at['model_after', 'hard_coal']]})
    d['before_ratio'] = d.before_twh / d.actual_twh
    d['after_ratio'] = d.after_twh / d.actual_twh
    fig, ax = plt.subplots(figsize=(7, 4.2))
    fig.subplots_adjust(left=0.10, right=0.97, top=0.76, bottom=0.17)
    x = range(len(d))
    w = 0.3
    for off, col, c, lab in ((-w / 2 - 0.01, 'before_ratio', BEFORE, 'Before the repair'),
                             (w / 2 + 0.01, 'after_ratio', AFTER, 'After the repair')):
        b = ax.bar([i + off for i in x], d[col], width=w, color=c, label=lab)
        for r in b:
            ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.03,
                    f'{r.get_height():.2f}×', ha='center', va='bottom', fontsize=10, color=INK)
    ax.axhline(1.0, color=INK, lw=1)
    ax.text(0.5, 1.03, 'actual = 1.0', ha='center', va='bottom', fontsize=9, color=INK2)
    ax.set_xticks(list(x), d.fuel, fontsize=10.5, color=INK)
    ax.set_ylim(0, 2.1)
    ax.set_ylabel('model generation ÷ actual generation')
    frame(ax)
    ax.legend(frameon=False, loc='upper right', fontsize=9, labelcolor=INK2)
    title(fig, 'Coal generation, model over actual, 2025',
          'Same 8,679 hours; actual = ENTSO-E generation by type (A75), Germany-Luxembourg')
    fig.savefig(out / 'fig_b_coal.png', dpi=200)
    d.round(3).to_csv(out / 'fig_b_coal.csv', index=False)


def fig_c(series, out):
    n = pd.read_csv(series / 'de_net_export_hourly.csv', parse_dates=['ts_utc'])
    ok = n[['model_before_mw', 'model_after_mw', 'actual_physical_mw']].notna().all(axis=1)
    n = n[ok].set_index('ts_utc')[['model_before_mw', 'model_after_mw', 'actual_physical_mw']]
    cum = n.cumsum() / 1e6
    fig, ax = plt.subplots(figsize=(8, 4.4))
    fig.subplots_adjust(left=0.09, right=0.76, top=0.80, bottom=0.10)
    for col, c, lab, lw in (('actual_physical_mw', INK, 'Actual', 2.4),
                            ('model_before_mw', BEFORE, 'Model, before', 2),
                            ('model_after_mw', AFTER, 'Model, after', 2)):
        ax.plot(cum.index, cum[col], color=c, lw=lw, solid_capstyle='round', label=lab)
        ax.plot(cum.index[-1], cum[col].iloc[-1], 'o', ms=7, color=c, mec=SURFACE, mew=2)
        ax.text(cum.index[-1] + pd.Timedelta(days=6), cum[col].iloc[-1],
                f'{lab}  {cum[col].iloc[-1]:+.1f} TWh', va='center', fontsize=9, color=INK)
    ax.axhline(0, color=INK2, lw=1)
    ax.set_ylabel('cumulative net export, TWh (+ = export)')
    frame(ax)
    ax.legend(frameon=False, loc='lower left', fontsize=9, labelcolor=INK2)
    title(fig, "Germany's net position through 2025",
          'Cumulative over the 8,679 hours both runs cleared; actual = ENTSO-E physical flows on '
          'ten borders')
    fig.savefig(out / 'fig_c_net.png', dpi=200)
    m = cum.resample('MS').last()
    m.index = m.index.strftime('%Y-%m')
    m.columns = ['model_before_twh', 'model_after_twh', 'actual_twh']
    m.round(2).to_csv(out / 'fig_c_net.csv')


def fig_d(series, out):
    s = pd.read_csv(series / 'de_price_setter_hourly.csv')
    lab = {'border': 'Set outside Germany', 'gas': 'Gas', 'lignite': 'Lignite',
           'hard_coal': 'Hard coal'}
    f = lambda v: lab.get(v, 'Other (solar, oil, hydro, wind)')   # noqa: E731
    d = pd.DataFrame({'before': s.setter_before.map(f).value_counts(),
                      'after': s.setter_after.map(f).value_counts()}).fillna(0).astype(int)
    d = d.loc[[lab['border'], 'Gas', 'Hard coal', 'Lignite', 'Other (solar, oil, hydro, wind)']]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    fig.subplots_adjust(left=0.30, right=0.95, top=0.80, bottom=0.10)
    y = range(len(d))
    h = 0.34
    for off, col, c, lb in ((-h / 2 - 0.01, 'before', BEFORE, 'Before the repair'),
                            (h / 2 + 0.01, 'after', AFTER, 'After the repair')):
        b = ax.barh([i + off for i in y], d[col], height=h, color=c, label=lb)
        for r, v in zip(b, d[col]):
            ax.text(r.get_width() + 60, r.get_y() + r.get_height() / 2, f'{v:,}', va='center',
                    fontsize=9, color=INK)
    ax.set_yticks(list(y), d.index, fontsize=10, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, d.values.max() * 1.15)
    ax.set_xlabel(f'hours of {len(s):,}')
    frame(ax, 'x')
    ax.legend(frameon=False, loc='lower right', fontsize=9, labelcolor=INK2)
    title(fig, "Who set Germany's day-ahead price in the model, 2025",
          'Hours in which the price-setting plant burned each fuel, or stood outside Germany')
    fig.savefig(out / 'fig_d_setters.png', dpi=200)
    d.rename_axis('price set by').to_csv(out / 'fig_d_setters.csv')


def main(series, fleet, out):
    series, fleet, out = Path(series), Path(fleet), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    fig_a(fleet, out)
    fig_b(series, out)
    fig_c(series, out)
    fig_d(series, out)
    print('figures ->', out)


if __name__ == '__main__':
    main(*sys.argv[1:4])
