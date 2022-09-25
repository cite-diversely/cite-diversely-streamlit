# This is our main interface library
# For main things
import types

import bibtexparser
import csv
import gender_guesser.detector
import nameparser
import operator
import os
import pandas
import pathlib
import pickle
import plotly.express
import streamlit
import st_aggrid


class References(object):
    def __init__(self, reference_text):
        self.gender_options = ['male', 'mostly_male', 'andy', 'mostly_female', "female", "unknown",
                               "first_name_initial"]
        self.gender_results = {key: 0 for key in self.gender_options}
        self.race_options = ['pctwhite', 'pctblack', 'pctapi', 'pctaian', 'pct2prace', 'pcthispanic', 'race_unknown']
        self.ethnicity_results = {key: 0 for key in self.race_options}
        self.raw_results = {}

        pickle_path = pathlib.Path(__file__).parent / 'data' / 'ethnicity_lookup.p'
        csv_path = pathlib.Path(__file__).parent / 'data' / 'Names_2010Census.csv'

        # Load data
        if os.path.isfile(pickle_path):
            self.ethnicity_lookup = pickle.load(open(pickle_path, 'rb'))
        else:
            self.ethnicity_lookup = {}
            with open(csv_path) as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    self.ethnicity_lookup[row['name']] = {}
                    for race in self.race_options[:-1]:
                        try:
                            value = float(row[race])
                        except ValueError:
                            value = 0
                        self.ethnicity_lookup[row['name']][race] = value
            pickle.dump(self.ethnicity_lookup, open(pickle_path, 'wb'))

        # Parse names from input
        self.reference_text = reference_text
        self.references = bibtexparser.loads(reference_text)
        self.first_names = []
        self.last_names = []
        self.raw_results = {'title': []}
        for paper in self.references.entries:
            if "author" in paper:
                authors = paper["author"].split(' and ')
                for person in authors:
                    self.raw_results['title'].append(paper['title'])
                    name = nameparser.HumanName(person)
                    self.first_names.append(name.first)
                    self.last_names.append(name.last)
        self.raw_results['first_name'] = self.first_names
        self.raw_results['last_name'] = self.last_names

    def infer_ethnicity(self):
        # Get ethnicity
        most_likely_race = []
        for name in self.last_names:
            if name.upper() in self.ethnicity_lookup:
                rr = max(self.ethnicity_lookup[name.upper()].items(), key=operator.itemgetter(1))[0]
                most_likely_race.append(rr)
            else:
                most_likely_race.append('race_unknown')
        self.raw_results['most_likely_race'] = most_likely_race

        for i in most_likely_race:
            self.ethnicity_results[i] = self.ethnicity_results.get(i, 0) + 1

    def infer_gender(self):
        # Get gender
        most_likely_gender = []
        d = gender_guesser.detector.Detector()
        for name in self.first_names:
            if (len(name) == 2 and name[1] == '.') or len(name) == 1:
                most_likely_gender.append("first_name_initial")
            else:
                most_likely_gender.append(d.get_gender(name))
        self.raw_results['most_likely_gender'] = most_likely_gender

        for i in most_likely_gender:
            self.gender_results[i] = self.gender_results.get(i, 0) + 1


label_to_gender = {'male': "Very Likely Male",
                   'mostly_male': "Likely Male",
                   'andy': "Hard to Tell",
                   'mostly_female': "Likely Female",
                   "female": "Very Likely Female",
                   "unknown": "Unknown (model inconclusive)",
                   "first_name_initial": "Unknown (first name initial only)"}

label_to_ethnicity = {'pctwhite': 'White',
                      'pctblack': 'Black',
                      'pctapi': 'Asian or Pacific Islander',
                      'pctaian': 'American Indian or Alaskan Native',
                      'pct2prace': 'Two or more races',
                      'pcthispanic': 'Hispanic',
                      'race_unknown': 'Unknown (not found in database)'}

ethnicity_to_label = {v: k for k, v in label_to_ethnicity.items()}
gender_to_label = {v: k for k, v in label_to_gender.items()}


def make_table():
    if 'table_data' in streamlit.session_state:
        df = streamlit.session_state['table_data']
    else:
        refs = References(streamlit.session_state.bib)
        refs.infer_gender()
        refs.infer_ethnicity()

        df = pandas.DataFrame(refs.raw_results["first_name"], columns=["First Name"])
        df = df.join(pandas.DataFrame(refs.raw_results["last_name"], columns=["Last Name"]))
        df = df.join(pandas.DataFrame([label_to_ethnicity[x] for x in refs.raw_results["most_likely_race"]],
                                      columns=["Most Likely Ethnicity"]))
        df = df.join(pandas.DataFrame([label_to_gender[x] for x in refs.raw_results["most_likely_gender"]],
                                      columns=["Most Likely Gender"]))
        df = df.join(pandas.DataFrame(refs.raw_results["title"], columns=["Title"]))
        df = df.sort_values(["Last Name", "First Name"])
        df = df.reset_index(drop=True)

    gb = st_aggrid.GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(editable=True)

    gb.configure_column('Most Likely Ethnicity',
                        cellEditor='agRichSelectCellEditor',
                        cellEditorParams={'values': list(label_to_ethnicity.values())},
                        cellEditorPopup=True
                        )

    gb.configure_column('Most Likely Gender',
                        cellEditor='agRichSelectCellEditor',
                        cellEditorParams={'values': list(label_to_gender.values())},
                        cellEditorPopup=True
                        )

    gb.configure_column('Title',
                        editable=False
                        )

    # gb.configure_grid_options(enableRangeSelection=True)

    response = st_aggrid.AgGrid(
        data=df,
        gridOptions=gb.build(),
        fit_columns_on_grid_load=True,
    )

    streamlit.session_state['table_data'] = response.data
    if response.column_state:
        streamlit.experimental_rerun()


# Define a function for addition
def make_results():
    data = streamlit.session_state['table_data']
    refs = types.SimpleNamespace(
        ethnicity_results=data['Most Likely Ethnicity'].value_counts().to_dict(),
        gender_results=data['Most Likely Gender'].value_counts().to_dict(),
    )

    plt1 = plotly.express.pie(
        names=list(refs.ethnicity_results.keys()),
        values=refs.ethnicity_results.values(),
        hole=0.5,
    )
    plt2 = plotly.express.pie(
        names=list(refs.gender_results.keys()),
        values=refs.gender_results.values(),
        hole=0.5,
    )
    plt3 = plotly.express.pie(
        names=list(refs.gender_results.keys()),
        values=refs.gender_results.values(),
        hole=0.5,
    )
    plt1.update_layout(legend=dict(orientation="h"))
    plt2.update_layout(legend=dict(orientation="h"))
    plt3.update_layout(legend=dict(orientation="h"))

    streamlit.plotly_chart(plt1, use_container_width=True)
    streamlit.plotly_chart(plt2, use_container_width=True)


streamlit.title("Welcome, and thank you")
streamlit.markdown("""Simply put, many people often cite people that are like them. This is a problem because academia has historically been white male dominated, leading to the suppression of marginalized voices. If your citations are biased towards people who look like you, then you are missing out on high-quality work.
    
Its important to note that using this site is not a replacement for truly being diligent and engaged in citing diverse voices. Rather, this site is just a place to start, and hopefully the first step in your journey of citing more diversely. To learn more about your duty to dismantle institutional oppression through your citation practices, read up here:
    
- [Cite Black Women](https://www.citeblackwomencollective.org)
- [The Racial Politics of Citation](https://www.insidehighered.com/advice/2018/04/27/racial-exclusions-scholarly-citations-opinion")
- [Inclusive Citation: How Diverse Are Your References?](https://blog.mahabali.me/writing/inclusive-citation-how-diverse-are-your-references/")
  
""")

streamlit.markdown("To use our tool, copy and paste your references in the box below and click on the "
                   "`Analyze` button.")

filler = """@article{Raina2019,
    author = {Raina, Ayush and McComb, Christopher and Cagan, Jonathan},
    title = {Learning to Design From Humans: Imitating Human Designers Through Deep Learning},
    journal = {Journal of Mechanical Design},
    volume = {141},
    number = {11},
    year = {2019},
    month = {09},
    issn = {1050-0472},
    doi = {10.1115/1.4044256}
}

@article{Williams2019,
    author = {Williams, Glen and Meisel, Nicholas A. and Simpson, Timothy W. and McComb, Christopher},
    title = {Design Repository Effectiveness for 3D Convolutional Neural Networks: Application to Additive Manufacturing},
    journal = {Journal of Mechanical Design},
    volume = {141},
    number = {11},
    year = {2019},
    month = {09},
    issn = {1050-0472},
    doi = {10.1115/1.4044199}
}"""
if "bib" in streamlit.session_state:
    filler = streamlit.session_state["bib"]

streamlit.text_area(".bibtex only for now, sorry!", filler, key="bib", height=250)
details = streamlit.sidebar
details.selectbox("Gender Inference Model", ("gender_guesser", "genderComputer"))
details.selectbox("Ethnicity Inference Model", ("ethnicolr - census data",
                                                  "ethnicolr - wikipedia data",
                                                  "ethnicolr - North Carolina data",
                                                  "ethnicolr - Florida registration data"))



placeholder = streamlit.empty()
time_to_analyze = placeholder.button("Analyze")
if time_to_analyze or 'already_analyzed' in streamlit.session_state:
    streamlit.session_state['already_analyzed'] = True
    placeholder.empty()
    with streamlit.spinner("Analyzing..."):
        streamlit.markdown("""This table display a tabular version of your results. You can also edit the inferred 
        ethnicity and gender to improve the accuracy of results.
                            """)
        make_table()

        placeholder2 = streamlit.empty()
        time_to_plot = placeholder2.button("Plot")
        if time_to_plot or 'already_plotted' in streamlit.session_state:
            streamlit.session_state['already_plotted'] = True
            placeholder2.empty()
            with streamlit.spinner("Plotting..."):
                streamlit.markdown("These tabs summarize your results with a variety of visualizations and statistics.")
                make_results()
