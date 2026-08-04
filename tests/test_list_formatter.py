"""Tests for Mudae list name extraction."""

from mudae.list_formatter import extract_character_names, format_mudae_character_list

RANKED_LIST = """
#1 - Hatsune Miku 💞 - VOCALOID
#2 - Zero Two 💞 - DARLING in the FRANXX
#3 - Rem 💞 - Re:Zero kara Hajimeru Isekai Seikatsu
#4 - Saber 💞 - Fate/stay night
#5 - Megumin 💞 - Kono Subarashii Sekai ni Shukufuku wo!
#6 - Rias Gremory 💞 - High School DxD
#7 - Power 💞 - Chainsaw Man
#8 - Nami 💞 - One Piece
#9 - Mai Sakurajima 💞 - Seishun Buta Yarou
#10 - 2B 💞 - NieR: Automata
#11 - Satoru Gojo - Jujutsu Kaisen
#12 - Makima 💞 - Chainsaw Man
#13 - Asuna 💞 - Sword Art Online
#14 - Albedo 💞 - Overlord
#15 - Mikasa Ackerman 💞 - Attack on Titan
""".strip()

RANKED_EXPECTED = [
    "Hatsune Miku",
    "Zero Two",
    "Rem",
    "Saber",
    "Megumin",
    "Rias Gremory",
    "Power",
    "Nami",
    "Mai Sakurajima",
    "2B",
    "Satoru Gojo",
    "Makima",
    "Asuna",
    "Albedo",
    "Mikasa Ackerman",
]

POINTS_LIST = (
    "82 - Hatsune Miku ~ VOCALOID#1 -"
    "68 - Power ~ Chainsaw Man#7 -"
    "45 - 2B ~ NieR: Automata#10 -"
    "69 - Makima ~ Chainsaw Man#12 -"
    "43 - Albedo ~ Overlord#14 -"
    "83 - Marin Kitagawa ~ Sono Bisque Doll wa Koi wo Suru#21 -"
    "84 - Frieren ~ Sousou no Frieren#24 -"
    "1 - Reze ~ Chainsaw Man#33 -"
    "85 - Yumeko Jabami ~ Kakegurui#35 -"
    "86 - Maki Zenin ~ Jujutsu Kaisen#44 -"
    "29 - Ai Hoshino ~ 【OSHI NO KO】#55 -"
    "18 - C.C. ~ Code Geass: Hangyaku no Lelouch#58 -"
    "98 - Jinx ~ League of Legends#60 -"
    "16 - Kurisu Makise ~ Steins;Gate#63 -"
    "36 - Kasane Teto ~ UTAU#79 -"
)

POINTS_EXPECTED = [
    "Hatsune Miku",
    "Power",
    "2B",
    "Makima",
    "Albedo",
    "Marin Kitagawa",
    "Frieren",
    "Reze",
    "Yumeko Jabami",
    "Maki Zenin",
    "Ai Hoshino",
    "C.C.",
    "Jinx",
    "Kurisu Makise",
    "Kasane Teto",
]

KAKERA_LIST = """
#1 - Hatsune Miku · ($wa, $wg) · :chaoskey:  (605) 58,625 ka
#2 - Zero Two · ($wa) · :chaoskey:  (179) 15,849 ka
#3 - Rem · ($wa) · :chaoskey:  (199) 17,415 ka
#4 - Saber · ($wa, $wg) · :chaoskey:  (160) 13,623 ka
#5 - Megumin · ($wa) · :chaoskey:  (198) 16,973 ka
#6 - Rias Gremory · ($wa) · :chaoskey:  (185) 15,566 ka
#7 - Power · ($wa) · :chaoskey:  (199) 16,498 ka
#8 - Nami · ($wa) · :chaoskey:  (217) 18,284 ka
#9 - Mai Sakurajima · ($wa) · :chaoskey:  (172) 13,803 ka
#10 - 2B · ($wa, $wg) · :chaoskey:  (502) 44,199 ka
#12 - Makima · ($wa) · :chaoskey:  (215) 17,171 ka
#13 - Asuna · ($wa) · :chaoskey:  (188) 15,477 ka
#14 - Albedo · ($wa) · :chaoskey:  (155) 12,195 ka
#15 - Mikasa Ackerman · ($wa) · :chaoskey:  (183) 14,596 ka
#16 - Nico Robin · ($wa) · :chaoskey:  (181) 13,936 ka
Image
""".strip()


def test_ranked_wishlist_format():
    assert extract_character_names(RANKED_LIST) == RANKED_EXPECTED


def test_ranked_wishlist_dollar_joined():
    assert format_mudae_character_list(RANKED_LIST) == "$".join(RANKED_EXPECTED)


def test_points_concatenated_format():
    assert extract_character_names(POINTS_LIST) == POINTS_EXPECTED


def test_kakera_stats_format():
    names = extract_character_names(KAKERA_LIST)
    assert names[0] == "Hatsune Miku"
    assert names[-1] == "Nico Robin"
    assert "Image" not in names
    assert len(names) == 15


def test_empty_input():
    assert extract_character_names("") == []
    assert format_mudae_character_list("   ") == ""
