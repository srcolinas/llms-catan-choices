use rand::Rng;
use rand::SeedableRng;
use rand::rngs::StdRng;
use rand::seq::SliceRandom;

use super::coordinates::{EdgeCoordinate, HexCoordinate, Index};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(
    feature = "serde",
    derive(serde::Deserialize),
    serde(rename_all = "lowercase")
)]
pub enum Terrain {
    Forest,
    Pasture,
    Fields,
    Hills,
    Mountains,
}

impl Terrain {
    /// The resource collected when this terrain's number is rolled.
    pub fn resource(self) -> Resource {
        match self {
            Self::Hills => Resource::Brick,
            Self::Mountains => Resource::Ore,
            Self::Fields => Resource::Wheat,
            Self::Forest => Resource::Wood,
            Self::Pasture => Resource::Sheep,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[cfg_attr(
    feature = "serde",
    derive(serde::Deserialize),
    serde(rename_all = "lowercase")
)]
pub enum Resource {
    Brick,
    Wood,
    Sheep,
    Wheat,
    Ore,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Deserialize))]
pub struct Tile {
    pub q: i8,
    pub r: i8,
    pub number: u8,
    pub terrain: Terrain,
}

const RESOURCE_QUANTITY: [(Terrain, u8); 5] = [
    (Terrain::Hills, 3),
    (Terrain::Mountains, 3),
    (Terrain::Fields, 4),
    (Terrain::Forest, 4),
    (Terrain::Pasture, 4),
];

#[derive(Debug, Clone, Copy)]
enum Land {
    Resource(Terrain),
    Desert,
}

/// Clockwise inward hexes, starting at (-2, 0) and ending at the center.
pub(crate) const PLACEMENT_SPIRAL: [(i8, i8); 19] = [
    (-2, 0),
    (-1, -1),
    (0, -2),
    (1, -2),
    (2, -2),
    (2, -1),
    (2, 0),
    (1, 1),
    (0, 2),
    (-1, 2),
    (-2, 2),
    (-2, 1),
    (-1, 0),
    (0, -1),
    (1, -1),
    (1, 0),
    (0, 1),
    (-1, 1),
    (0, 0),
];

/// Number tokens in rulebook letter order A–R.
const NUMBER_TOKENS: [u8; 18] = [5, 2, 6, 3, 8, 10, 9, 12, 11, 4, 8, 10, 9, 4, 5, 6, 3, 11];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HarbourKind {
    Generic,
    Specific(Resource),
}

#[cfg(feature = "serde")]
impl<'de> serde::Deserialize<'de> for HarbourKind {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        match value.as_str() {
            "generic" => Ok(Self::Generic),
            "wood" => Ok(Self::Specific(Resource::Wood)),
            "brick" => Ok(Self::Specific(Resource::Brick)),
            "sheep" => Ok(Self::Specific(Resource::Sheep)),
            "ore" => Ok(Self::Specific(Resource::Ore)),
            "wheat" => Ok(Self::Specific(Resource::Wheat)),
            _ => Err(serde::de::Error::custom(format!(
                "unknown harbour kind {value}"
            ))),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Deserialize))]
pub struct Harbour {
    pub edge: EdgeCoordinate,
    pub kind: HarbourKind,
}

/// Base-game harbours as `(q, r, edge, kind)`: four 3:1 ports, then the five 2:1 ports.
const HARBOURS: [(i8, i8, Index, HarbourKind); 9] = [
    (0, -2, Index::Five, HarbourKind::Generic),
    (-2, 2, Index::Three, HarbourKind::Generic),
    (-1, 2, Index::Two, HarbourKind::Generic),
    (2, 0, Index::One, HarbourKind::Generic),
    (-1, -1, Index::Four, HarbourKind::Specific(Resource::Wood)),
    (-2, 1, Index::Four, HarbourKind::Specific(Resource::Brick)),
    (1, 1, Index::Two, HarbourKind::Specific(Resource::Sheep)),
    (2, -1, Index::Zero, HarbourKind::Specific(Resource::Ore)),
    (1, -2, Index::Zero, HarbourKind::Specific(Resource::Wheat)),
];

#[derive(Debug, Clone, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Deserialize))]
pub struct Board {
    pub tiles: [Tile; 18],
    pub desert: HexCoordinate,
    pub harbours: [Harbour; 9],
}

impl Board {
    pub fn from_seed(seed: u64) -> Self {
        let mut rng = StdRng::seed_from_u64(seed);
        Self::from_rng(&mut rng)
    }

    pub(crate) fn from_rng(rng: &mut impl Rng) -> Self {
        let mut lands = terrain_bag();
        lands.shuffle(rng);
        assemble(lands)
    }
}

#[inline]
fn terrain_bag() -> [Land; 19] {
    let mut lands = [Land::Desert; 19];
    let mut index = 0;
    for (terrain, count) in RESOURCE_QUANTITY {
        for _ in 0..count {
            lands[index] = Land::Resource(terrain);
            index += 1;
        }
    }
    lands
}

#[inline]
fn assemble(lands: [Land; 19]) -> Board {
    let mut numbers = NUMBER_TOKENS.into_iter();
    let mut tiles = Vec::with_capacity(18);
    let mut desert = None;
    for ((q, r), land) in PLACEMENT_SPIRAL.into_iter().zip(lands) {
        match land {
            Land::Desert => desert = Some(HexCoordinate { q, r }),
            Land::Resource(terrain) => tiles.push(Tile {
                q,
                r,
                number: numbers.next().expect("one number per non-desert tile"),
                terrain,
            }),
        }
    }
    Board {
        tiles: tiles.try_into().expect("18 numbered tiles"),
        desert: desert.expect("one desert"),
        harbours: HARBOURS.map(|(q, r, edge, kind)| Harbour {
            edge: EdgeCoordinate::new(q, r, edge),
            kind,
        }),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rstest::rstest;

    #[test]
    fn terrain_maps_to_its_resource() {
        assert_eq!(Terrain::Hills.resource(), Resource::Brick);
        assert_eq!(Terrain::Mountains.resource(), Resource::Ore);
        assert_eq!(Terrain::Fields.resource(), Resource::Wheat);
        assert_eq!(Terrain::Forest.resource(), Resource::Wood);
        assert_eq!(Terrain::Pasture.resource(), Resource::Sheep);
    }

    fn numbered_values(board: &Board) -> [u8; 18] {
        board.tiles.map(|tile| tile.number)
    }

    fn lands_with_desert_at(index: usize) -> [Land; 19] {
        let mut lands = [Land::Resource(Terrain::Forest); 19];
        lands[index] = Land::Desert;
        lands
    }

    #[rstest]
    #[case(0)]
    #[case(9)]
    #[case(18)]
    fn desert_is_skipped_when_assigning_numbers(#[case] desert_at: usize) {
        let board = assemble(lands_with_desert_at(desert_at));
        let (q, r) = PLACEMENT_SPIRAL[desert_at];
        assert_eq!(numbered_values(&board), NUMBER_TOKENS);
        assert_eq!(board.desert, HexCoordinate { q, r });
        assert!(board.tiles.iter().all(|tile| (tile.q, tile.r) != (q, r)));
    }

    #[rstest]
    #[case(0)]
    #[case(1)]
    #[case(42)]
    fn seeded_board_matches_invariants(#[case] seed: u64) {
        let board = Board::from_seed(seed);
        assert_eq!(board.tiles.len(), 18);

        let mut counts = [0u8; 5];
        for tile in &board.tiles {
            let index = match tile.terrain {
                Terrain::Hills => 0,
                Terrain::Mountains => 1,
                Terrain::Fields => 2,
                Terrain::Forest => 3,
                Terrain::Pasture => 4,
            };
            counts[index] += 1;
        }
        assert_eq!(counts, RESOURCE_QUANTITY.map(|(_, count)| count));

        assert_eq!(numbered_values(&board), NUMBER_TOKENS);
        let mut positions: Vec<(i8, i8)> =
            board.tiles.iter().map(|tile| (tile.q, tile.r)).collect();
        positions.push((board.desert.q, board.desert.r));
        positions.sort_unstable();
        let mut spiral = PLACEMENT_SPIRAL;
        spiral.sort_unstable();
        assert_eq!(positions, spiral);

        assert_eq!(
            board.harbours,
            HARBOURS.map(|(q, r, edge, kind)| Harbour {
                edge: EdgeCoordinate::new(q, r, edge),
                kind,
            })
        );

        // Seeded boards are deterministic
        assert_eq!(Board::from_seed(seed), board);
    }
}

#[cfg(all(test, feature = "serde"))]
mod serde_tests {
    use super::{Harbour, HarbourKind, Index, Resource, Terrain};

    #[test]
    fn terrain_deserializes_lowercase() {
        let cases = [
            ("\"forest\"", Terrain::Forest),
            ("\"pasture\"", Terrain::Pasture),
            ("\"fields\"", Terrain::Fields),
            ("\"hills\"", Terrain::Hills),
            ("\"mountains\"", Terrain::Mountains),
        ];
        for (json, expected) in cases {
            assert_eq!(serde_json::from_str::<Terrain>(json).unwrap(), expected);
        }
        assert!(serde_json::from_str::<Terrain>("\"Pasture\"").is_err());
    }

    #[test]
    fn harbour_kind_deserializes_flat_string() {
        let cases = [
            ("\"generic\"", HarbourKind::Generic),
            ("\"wood\"", HarbourKind::Specific(Resource::Wood)),
            ("\"brick\"", HarbourKind::Specific(Resource::Brick)),
            ("\"sheep\"", HarbourKind::Specific(Resource::Sheep)),
            ("\"ore\"", HarbourKind::Specific(Resource::Ore)),
            ("\"wheat\"", HarbourKind::Specific(Resource::Wheat)),
        ];
        for (json, expected) in cases {
            assert_eq!(serde_json::from_str::<HarbourKind>(json).unwrap(), expected);
        }
        assert!(serde_json::from_str::<HarbourKind>("\"stone\"").is_err());
    }

    #[test]
    fn harbour_deserializes_python_record() {
        let harbour: Harbour =
            serde_json::from_str(r#"{"edge":{"q":-2,"r":-1,"index":1},"kind":"wood"}"#).unwrap();
        assert_eq!(harbour.kind, HarbourKind::Specific(Resource::Wood));
        assert_eq!(harbour.edge.q, -2);
        assert_eq!(harbour.edge.r, -1);
        assert_eq!(harbour.edge.index, Index::One);
    }
}
