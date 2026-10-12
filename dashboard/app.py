"""Dashboard des DPE : passoires thermiques et performance énergétique.

Lit uniquement les tables gold, en Parquet sur S3, avec une clé en lecture seule (ADR-0003).
Charte graphique : natchiadata.dev (environ 90 % de neutres, l'orange pour ce qui doit
attirer l'œil).
"""

import altair as alt
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.fs as pafs
import streamlit as st

# --- Constantes métier --------------------------------------------------------

PASSOIRES = ["F", "G"]
PLAGES_ENERGIE = {
    "A": "≤ 70",
    "B": "70 à 110",
    "C": "110 à 180",
    "D": "180 à 250",
    "E": "250 à 330",
    "F": "330 à 420",
    "G": "> 420",
}
EFFECTIF_MINIMUM = 500  # en dessous, une proportion départementale est trop instable
NB_DEPARTEMENTS_AFFICHES = 20
NB_DEPARTEMENTS_MIS_EN_AVANT = 5

# --- Charte graphique de natchiadata.dev ----------------------------------------

ENCRE = "#0F1B2D"  # ink : éléments principaux
ACCENT = "#C2410C"  # accent : ce qui doit attirer l'œil
ACCENT_PALE = "#FFF1E8"  # accent-soft
GRIS_MOYEN = "#94A3B8"  # night-muted
BLANC = "#FFFFFF"

st.set_page_config(
    page_title="DPE : passoires et performance énergétique",
    layout="wide",
)


# --- Accès aux données --------------------------------------------------------


@st.cache_resource
def systeme_fichiers() -> pafs.S3FileSystem:
    """Connexion à S3 avec la clé en lecture seule du dashboard."""
    secrets = st.secrets["aws"]
    return pafs.S3FileSystem(
        access_key=secrets["access_key_id"],
        secret_key=secrets["secret_access_key"],
        region=secrets["region"],
    )


@st.cache_data(ttl=3600)
def lire_table(nom: str) -> pd.DataFrame:
    """Lit une table gold : tous les fichiers Parquet de son dossier."""
    bucket = st.secrets["aws"]["bucket_gold"]
    jeu = ds.dataset(f"{bucket}/{nom}/", format="parquet", filesystem=systeme_fichiers())
    return jeu.to_table().to_pandas()


@st.cache_data(ttl=3600)
def date_mise_a_jour() -> str:
    """Date de la dernière matérialisation de gold."""
    bucket = st.secrets["aws"]["bucket_gold"]
    selecteur = pafs.FileSelector(f"{bucket}/gold_dpe_departement/")
    dates = [info.mtime for info in systeme_fichiers().get_file_info(selecteur) if info.mtime]
    return max(dates).strftime("%d/%m/%Y") if dates else "inconnue"


def ordre_periodes(periodes: pd.Series) -> list[str]:
    """Trie les périodes de construction : « avant … » d'abord, puis chronologiquement."""
    return sorted(
        periodes.dropna().unique(),
        key=lambda p: (not str(p).startswith("avant"), str(p)),
    )


def formater_entier(nombre: int) -> str:
    """Affiche un entier avec une espace fine comme séparateur des milliers."""
    return f"{nombre:,}".replace(",", "\u202f")


# --- En-tête ------------------------------------------------------------------

st.title("Passoires thermiques et performance énergétique des logements")
st.caption(
    "DPE établis depuis juin 2026 · Source : ADEME, Licence Ouverte · "
    f"Données mises à jour le {date_mise_a_jour()}"
)
st.info(
    "Un DPE n'est établi qu'à la vente, à la location ou à la construction d'un logement : "
    "ces chiffres décrivent les **DPE établis**, pas l'ensemble du parc immobilier."
)

with st.sidebar:
    type_logement = st.radio("Type de logement", ["existant", "neuf"], index=0)
    st.markdown("---")
    st.markdown(
        "Plateforme de données construite sur AWS : ingestion de l'API de l'ADEME, "
        "couches bronze, silver et gold, requêtes Athena, infrastructure Terraform, "
        "pipeline GitHub Actions."
    )
    st.markdown("[natchiadata.dev](https://natchiadata.dev)")

departements = lire_table("gold_dpe_departement")
departements = departements[departements["type_logement"] == type_logement]

if departements.empty:
    st.error("Aucune donnée disponible pour ce type de logement.")
    st.stop()

# --- Indicateurs clés ---------------------------------------------------------

total = int(departements["nb_dpe"].sum())
par_etiquette = departements.groupby("etiquette_dpe")["nb_dpe"].sum() / total
part_deduits = departements["nb_dpe_departement_deduit"].sum() / total

colonnes = st.columns(4)
colonnes[0].metric("DPE analysés", formater_entier(total))
colonnes[1].metric("Passoires (F et G)", f"{par_etiquette.reindex(PASSOIRES).sum():.1%}")
colonnes[2].metric("Classés G", f"{par_etiquette.get('G', 0):.1%}")
colonnes[3].metric("Département déduit du code postal", f"{part_deduits:.1%}")

if type_logement == "existant":
    st.markdown(
        "**Calendrier d'interdiction de mise en location** (loi Climat et Résilience) : "
        f"logements G depuis 2025 (**{par_etiquette.get('G', 0):.1%}** des DPE), "
        f"F à partir de 2028 (**{par_etiquette.get('F', 0):.1%}**), "
        f"E à partir de 2034 (**{par_etiquette.get('E', 0):.1%}**)."
    )

# --- Départements -------------------------------------------------------------

if type_logement == "existant":
    st.header("Où sont les passoires ?")

    par_departement = departements.assign(
        nb_passoires=departements["nb_dpe"].where(departements["etiquette_dpe"].isin(PASSOIRES), 0)
    )
    par_departement = par_departement.groupby("code_departement", as_index=False)[
        ["nb_dpe", "nb_passoires"]
    ].sum()
    par_departement["part_passoires"] = par_departement["nb_passoires"] / par_departement["nb_dpe"]
    par_departement = par_departement[par_departement["nb_dpe"] >= EFFECTIF_MINIMUM]

    top = par_departement.nlargest(NB_DEPARTEMENTS_AFFICHES, "part_passoires").reset_index(
        drop=True
    )
    top["mise_en_avant"] = top.index < NB_DEPARTEMENTS_MIS_EN_AVANT

    st.altair_chart(
        alt.Chart(top)
        .mark_bar()
        .encode(
            x=alt.X(
                "part_passoires:Q",
                title="Part de passoires (F et G)",
                axis=alt.Axis(format="%"),
            ),
            y=alt.Y("code_departement:N", sort="-x", title="Département"),
            color=alt.condition("datum.mise_en_avant", alt.value(ACCENT), alt.value(ENCRE)),
            tooltip=[
                alt.Tooltip("code_departement:N", title="Département"),
                alt.Tooltip("nb_dpe:Q", title="DPE"),
                alt.Tooltip("part_passoires:Q", title="Part de passoires", format=".1%"),
            ],
        )
    )
    st.caption(
        f"Les {NB_DEPARTEMENTS_AFFICHES} départements à la plus forte part de passoires, "
        f"parmi ceux qui comptent au moins {EFFECTIF_MINIMUM} DPE. "
        f"Les {NB_DEPARTEMENTS_MIS_EN_AVANT} plus touchés sont en orange."
    )
else:
    st.header("Répartition des étiquettes énergie")

    repartition = par_etiquette.rename("part").reset_index()
    st.altair_chart(
        alt.Chart(repartition)
        .mark_bar(color=ENCRE)
        .encode(
            x=alt.X("etiquette_dpe:O", title="Étiquette énergie", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("part:Q", title="Part des DPE", axis=alt.Axis(format="%")),
            tooltip=[
                alt.Tooltip("etiquette_dpe:O", title="Étiquette"),
                alt.Tooltip("part:Q", title="Part des DPE", format=".1%"),
            ],
        )
    )
    st.caption(
        "Les logements neufs, soumis aux réglementations thermiques récentes, ne comptent "
        "quasiment aucune passoire : l'analyse des passoires porte sur les logements existants."
    )

# --- Double seuil -------------------------------------------------------------

st.header("Énergie ou émissions : qu'est-ce qui déclasse les logements ?")
st.markdown(
    "Depuis 2021, l'étiquette retient la **plus mauvaise** des deux classes : consommation "
    "d'énergie et émissions de gaz à effet de serre. Un logement peut être classé F ou G "
    "à cause de ses émissions (chauffage au fioul ou au gaz) plutôt que de sa consommation."
)

croisement = lire_table("gold_dpe_croisement_etiquettes")
croisement = croisement[croisement["type_logement"] == type_logement]
seuil_texte_clair = croisement["nb_dpe"].max() * 0.5

base = alt.Chart(croisement).encode(
    x=alt.X("etiquette_ges:O", title="Étiquette GES"),
    y=alt.Y("etiquette_dpe:O", title="Étiquette énergie"),
)
st.altair_chart(
    base.mark_rect().encode(
        color=alt.Color(
            "nb_dpe:Q",
            title="DPE",
            scale=alt.Scale(range=[ACCENT_PALE, ACCENT]),
        ),
        tooltip=[
            alt.Tooltip("etiquette_dpe:O", title="Étiquette énergie"),
            alt.Tooltip("etiquette_ges:O", title="Étiquette GES"),
            alt.Tooltip("nb_dpe:Q", title="DPE"),
        ],
    )
    + base.mark_text(fontSize=11).encode(
        text="nb_dpe:Q",
        color=alt.condition(
            f"datum.nb_dpe > {seuil_texte_clair}",
            alt.value(BLANC),
            alt.value(ENCRE),
        ),
    )
)
st.caption(
    "Aucune case au-dessus de la diagonale : l'étiquette finale n'est jamais meilleure que "
    "l'étiquette GES, conformément à la règle du double seuil. Sur la diagonale, les émissions "
    "peuvent être à l'origine du classement ; à gauche de la diagonale, c'est la consommation "
    "qui déclasse le logement (souvent un chauffage électrique dans un logement mal isolé)."
)

# --- Consommation par étiquette -----------------------------------------------

st.header("Consommation selon l'étiquette énergie")

energie = lire_table("gold_dpe_etiquette_energie")
energie = energie[energie["type_logement"] == type_logement].sort_values("etiquette_dpe")

st.dataframe(
    pd.DataFrame(
        {
            "Étiquette": energie["etiquette_dpe"],
            "DPE": energie["nb_dpe"],
            "Plage de la classe (kWh/m²/an)": energie["etiquette_dpe"].map(PLAGES_ENERGIE),
            "Médiane": energie["conso_ep_m2_mediane"].round().astype(int),
            "Moyenne": energie["conso_ep_m2_moyenne"].round().astype(int),
        }
    ),
    hide_index=True,
)

st.caption(
    "Une médiane située sous la plage de sa classe signale des logements"
    "déclassés par leurs émissions."
)

# --- Surface ------------------------------------------------------------------

if type_logement == "existant":
    st.header("Les petites surfaces sont-elles pénalisées ?")

    surface = lire_table("gold_dpe_surface")
    st.altair_chart(
        alt.Chart(surface)
        .mark_bar()
        .encode(
            x=alt.X("tranche_surface:N", title="Surface habitable", axis=alt.Axis(labelAngle=0)),
            xOffset="type_batiment:N",
            y=alt.Y(
                "part_passoires:Q",
                title="Part de passoires (F et G)",
                axis=alt.Axis(format="%"),
            ),
            color=alt.Color(
                "type_batiment:N",
                title="Type de bâtiment",
                scale=alt.Scale(
                    domain=["appartement", "maison", "immeuble"],
                    range=[ACCENT, ENCRE, GRIS_MOYEN],
                ),
            ),
            tooltip=[
                alt.Tooltip("tranche_surface:N", title="Surface"),
                alt.Tooltip("type_batiment:N", title="Type de bâtiment"),
                alt.Tooltip("nb_dpe:Q", title="DPE"),
                alt.Tooltip("part_passoires:Q", title="Part de passoires", format=".1%"),
            ],
        )
    )
    st.caption(
        "Corrélation, pas causalité : les petites surfaces sont aussi plus souvent anciennes "
        "ou situées en centre-ville."
    )

# --- Ancienneté ---------------------------------------------------------------

if type_logement == "existant":
    st.header("Performance selon la période de construction")

    periodes = lire_table("gold_dpe_periode_construction")
    periodes = periodes[periodes["type_logement"] == type_logement]

    st.altair_chart(
        alt.Chart(periodes)
        .mark_bar(color=ENCRE)
        .encode(
            x=alt.X(
                "periode_construction:N",
                sort=ordre_periodes(periodes["periode_construction"]),
                title="Période de construction",
                axis=alt.Axis(labelAngle=-30),
            ),
            y=alt.Y(
                "part_passoires:Q",
                title="Part de passoires (F et G)",
                axis=alt.Axis(format="%"),
            ),
            tooltip=[
                alt.Tooltip("periode_construction:N", title="Période"),
                alt.Tooltip("nb_dpe:Q", title="DPE"),
                alt.Tooltip("conso_ep_m2_mediane:Q", title="Conso. médiane", format=".0f"),
                alt.Tooltip("part_passoires:Q", title="Part de passoires", format=".1%"),
            ],
        )
    )

# --- Méthodologie -------------------------------------------------------------

with st.expander("Méthodologie et limites"):
    st.markdown(
        """
- **Source** : API de l'ADEME, DPE logements existants et neufs, ingérés chaque semaine.
- **Dédoublonnage** : une ligne par DPE, sa version la plus récente.
- **Département** : celui du géocodage de l'adresse (BAN) ; à défaut, déduit du code postal
  saisi par le diagnostiqueur (part indiquée en haut de page).
- **Médianes approchées** (`approx_percentile` d'Athena).
- **Délai de publication** : l'ADEME publie les DPE par lots, avec plusieurs jours de retard ;
  les dernières semaines sont incomplètes.
- **Représentativité** : la base ne couvre que les DPE établis, pas l'ensemble du parc.
"""
    )
