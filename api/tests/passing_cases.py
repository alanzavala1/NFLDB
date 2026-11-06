"""A consistent per-play passing source and independent native export fixture."""
import numpy as np
import pandas as pd

from pipeline.passing_down import COUNTS


def metric_case(year=2024):
    plays, credits = [], []
    for i in range(51):
        backup = i == 50
        completed = i < 20 or 25 <= i < 40 or backup
        intercepted = i in (24, 49)
        td = i in (0, 1, 2, 25)
        yards = (14 if backup else 60 if i == 0 else 10) if completed else 0
        player = 'backup' if backup else 'qb'
        plays.append(dict(game_id='game', play_id=i, season=year, season_type='REG',
            down=1 if i < 25 or backup else 2, passer_player_id=player, pass_attempt=1,
            sack=0, two_point_attempt=0, play_type='pass', complete_pass=int(completed),
            incomplete_pass=int(not completed and not intercepted), interception=int(intercepted),
            passing_yards=yards if completed else np.nan, pass_touchdown=int(td),
            first_down=int(completed and i % 2 == 0), qb_epa=0.5 if completed else -1.0,
            epa=0.5 if completed else -1.0, cpoe=4.0 if i % 3 else np.nan,
            air_yards=yards - 4 if completed else 10, yards_after_catch=4 if completed else np.nan))
        credits.append(dict(game_id='game', play_id=i, gsis_player_id=player,
                            stat_id=16 if td else 15 if completed else 19 if intercepted else 14, yards=yards))
    context = pd.DataFrame(plays)
    credits = pd.DataFrame(credits)
    # Explicit independent expected totals; model sums follow the known sequence.
    raw = pd.DataFrame([
        ['qb','1',25,20,250,3,1,0,220,80,10,5.0,4.0],
        ['qb','2',25,15,150,1,1,0,190,60,7,-2.5,4.0],
        ['backup','1',1,1,14,0,0,0,10,4,1,0.5,4.0],
    ], columns=['player_id','split_value',*COUNTS,'passing_air_yards','passing_yards_after_catch',
                'passing_first_downs','passing_epa','passing_cpoe'])
    raw = raw.assign(season=year, season_type='REG')
    whole = raw.groupby(['player_id','season','season_type'],as_index=False)[[*COUNTS,'passing_first_downs']].sum()
    return dict(context=context, credits=credits, down=raw, whole=whole,
                classified=whole.copy(), excluded=whole.iloc[:0].copy(), weekly=whole.copy(), season=year)


VIEW_LABELS = {
    'down':('1','2'), 'quarter':('1','2'), 'home_away':('home','away'),
    'shotgun':('shotgun','under_center'), 'field_zone':('own_territory','opp_territory'),
    'game_script':('leading','tied'), 'no_huddle':('huddle','no_huddle'),
    'game_state':('competitive','garbage'), 'roof':('dome','outdoors'),
    'surface':('grass','turf'), 'opponent':('NYJ','SEA'), 'opp_division':('AFC East','NFC West'),
    'pass_depth':('short','deep'), 'pass_location':('left','middle'), 'pressure':('clean','pressured'),
    'play_action':('play_action','no_pa'), 'blitz':('standard_rush','blitz')}


def view_case(dimension, year=2024):
    data=metric_case(year)
    p=data['context'];first=p.down.eq(1)
    for field,a,b in (('qtr',1,2),('posteam_type','home','away'),('shotgun',1,0),
        ('yardline_100',70,40),('score_differential',7,0),('no_huddle',0,1),('wp',.5,.99),
        ('roof','dome','outdoors'),('surface','grass','fieldturf'),('defteam','NYJ','SEA'),
        ('pass_length','short','deep'),('pass_location','left','middle'),('qb_hit',0,1),
        ('is_play_action',1,0),('n_pass_rushers',3,6)):
        p[field]=np.where(first,a,b)
    a,b=VIEW_LABELS[dimension]
    if dimension=='pressure' and year<2006 or dimension in ('play_action','blitz') and year<2022:
        a,b=None,None
    labels=p.down.astype('string').map({'1':a,'2':b}).astype('string')
    raw=data['down'].copy()
    raw['split_value']=raw.split_value.map({'1':a,'2':b}).astype('string')
    def aggregate(frame):
        sums=[*COUNTS,'passing_air_yards','passing_yards_after_catch','passing_first_downs','passing_epa']
        return frame.groupby(['player_id','season','season_type'],as_index=False).agg(
            {**{field:'sum' for field in sums},'passing_cpoe':'mean'})
    data['whole']=aggregate(raw)
    data['classified']=aggregate(raw.loc[raw.split_value.notna()])
    data['excluded']=aggregate(raw.loc[raw.split_value.isna()])
    data['down']=raw.loc[raw.split_value.notna()].copy()
    data['weekly']=data['whole'].copy()
    return data,labels
