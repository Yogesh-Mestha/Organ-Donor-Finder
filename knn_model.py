import pandas as pd
from sklearn.preprocessing import LabelEncoder
from sklearn.neighbors import NearestNeighbors

def load_and_preprocess_data(path='donor_data.csv'):
    df = pd.read_csv(path)
    encoders = {}
    for col in ['Blood Type','HLA Typing','Organ Type','State','City']:
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col].astype(str))
        encoders[col] = le
    return df, encoders

def find_matching_donors(patient_data, k=10, age_range=2, csv_path='donor_data.csv'):
    df, enc = load_and_preprocess_data(csv_path)
    enc_vals = {c: enc[c].transform([str(patient_data[c])])[0] for c in enc}
    mask = True
    for c, v in enc_vals.items():
        mask &= (df[c] == v)
    filtered = df[mask]
    if filtered.empty: return []
    age = patient_data['Age']
    init = filtered[filtered['Age'].between(age - age_range, age + age_range)]
    if len(init) >= k:
        nn = NearestNeighbors(n_neighbors=k).fit(init[['BMI']])
        d, i = nn.kneighbors([[patient_data['BMI']]])
        result = init.iloc[i[0]].copy()
    else:
        result = init.copy()
        rem = k - len(init)
        other = filtered[~filtered['Age'].between(age - age_range, age + age_range)]
        if not other.empty:
            cols = ['BMI','Age'] if len(other.columns) >= 2 else ['BMI']
            nn = NearestNeighbors(n_neighbors=min(rem, len(other))).fit(other[['BMI','Age']])
            d, i = nn.kneighbors([[patient_data['BMI'], age]])
            result = pd.concat([result, other.iloc[i[0]]])
    for c, le in enc.items():
        result[c] = le.inverse_transform(result[c])
    out = result.dropna().to_dict(orient='records')
    # add hospital column if exists in CSV
    if 'Hospital' in pd.read_csv(csv_path).columns:
        for r in out:
            # find hospital from original CSV
            orig = pd.read_csv(csv_path)
            m = orig[
                (orig['Name']==r['Name']) &
                (orig['Blood Type']==r['Blood Type'])
            ]
            r['Hospital'] = m.iloc[0]['Hospital'] if not m.empty else 'Unknown'
    return out
