use std::cmp::min;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Deserialize))]
pub struct HexCoordinate {
    pub q: i8,
    pub r: i8,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Index {
    Zero,
    One,
    Two,
    Three,
    Four,
    Five,
}

#[cfg(feature = "serde")]
impl<'de> serde::Deserialize<'de> for Index {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        match u8::deserialize(deserializer)? {
            0 => Ok(Self::Zero),
            1 => Ok(Self::One),
            2 => Ok(Self::Two),
            3 => Ok(Self::Three),
            4 => Ok(Self::Four),
            5 => Ok(Self::Five),
            other => Err(serde::de::Error::custom(format!(
                "index must be from 0 to 5, got {other}"
            ))),
        }
    }
}

impl Index {
    pub const ALL: [Self; 6] = [
        Self::Zero,
        Self::One,
        Self::Two,
        Self::Three,
        Self::Four,
        Self::Five,
    ];

    pub fn clockwise(self) -> Self {
        next_clockwise(self)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Deserialize))]
pub struct EdgeCoordinate {
    pub q: i8,
    pub r: i8,
    pub index: Index,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Deserialize))]
pub struct VertexCoordinate {
    pub q: i8,
    pub r: i8,
    pub index: Index,
}

impl EdgeCoordinate {
    /// Every edge is shared by two hexes, so pick the smaller `(q, r, index)`
    /// of the two aliases as the single canonical representation.
    pub fn new(q: i8, r: i8, edge: Index) -> Self {
        let hex = HexCoordinate { q, r };
        let (dq, dr) = index_to_offset(edge);
        let alias = HexCoordinate {
            q: hex.q + dq,
            r: hex.r + dr,
        };
        let (q, r, edge) = min((hex.q, hex.r, edge), (alias.q, alias.r, opposite(edge)));
        Self { q, r, index: edge }
    }

    /// The two corners of this edge, in canonical form.
    ///
    /// Edge `index` runs from vertex `index` to the next clockwise vertex.
    pub fn vertices(self) -> [VertexCoordinate; 2] {
        [
            VertexCoordinate::new(self.q, self.r, self.index),
            VertexCoordinate::new(self.q, self.r, self.index.clockwise()),
        ]
    }
}

impl VertexCoordinate {
    /// Every vertex is shared by three hexes, so pick the smaller `(q, r, index)`
    /// of the three aliases as the single canonical representation.
    ///
    /// Vertex `v` is the corner between edges `v` and `v - 1`. Crossing an edge
    /// reverses clockwise order, so that corner is index `v + 4` (mod 6) on the
    /// neighbor across edge `v`, and index `v + 2` (mod 6) on the neighbor
    /// across edge `v - 1`.
    pub fn new(q: i8, r: i8, vertex: Index) -> Self {
        let hex = HexCoordinate { q, r };
        let prev = next_counterclockwise(vertex);
        let (dq, dr) = index_to_offset(vertex);
        let (dq_prev, dr_prev) = index_to_offset(prev);
        let alias = HexCoordinate {
            q: hex.q + dq,
            r: hex.r + dr,
        };
        let alias_prev = HexCoordinate {
            q: hex.q + dq_prev,
            r: hex.r + dr_prev,
        };
        let (q, r, vertex) = min(
            (hex.q, hex.r, vertex),
            min(
                (alias.q, alias.r, opposite(next_clockwise(vertex))),
                (alias_prev.q, alias_prev.r, opposite(prev)),
            ),
        );
        Self {
            q,
            r,
            index: vertex,
        }
    }

    /// The three hexes that meet at this corner. Hexes off the island are water.
    pub fn hexes(self) -> [HexCoordinate; 3] {
        let hex = HexCoordinate {
            q: self.q,
            r: self.r,
        };
        let previous = next_counterclockwise(self.index);
        let (dq, dr) = index_to_offset(self.index);
        let (dq_prev, dr_prev) = index_to_offset(previous);
        [
            hex,
            HexCoordinate {
                q: hex.q + dq,
                r: hex.r + dr,
            },
            HexCoordinate {
                q: hex.q + dq_prev,
                r: hex.r + dr_prev,
            },
        ]
    }
}

#[inline]
fn index_to_offset(i: Index) -> (i8, i8) {
    match i {
        Index::Zero => (1, -1),
        Index::One => (1, 0),
        Index::Two => (0, 1),
        Index::Three => (-1, 1),
        Index::Four => (-1, 0),
        Index::Five => (0, -1),
    }
}

#[inline]
fn opposite(i: Index) -> Index {
    match i {
        Index::Zero => Index::Three,
        Index::One => Index::Four,
        Index::Two => Index::Five,
        Index::Three => Index::Zero,
        Index::Four => Index::One,
        Index::Five => Index::Two,
    }
}

#[inline]
fn next_counterclockwise(i: Index) -> Index {
    match i {
        Index::Zero => Index::Five,
        Index::One => Index::Zero,
        Index::Two => Index::One,
        Index::Three => Index::Two,
        Index::Four => Index::Three,
        Index::Five => Index::Four,
    }
}

#[inline]
fn next_clockwise(i: Index) -> Index {
    match i {
        Index::Zero => Index::One,
        Index::One => Index::Two,
        Index::Two => Index::Three,
        Index::Three => Index::Four,
        Index::Four => Index::Five,
        Index::Five => Index::Zero,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rstest::rstest;

    #[rstest]
    #[case(((0, 0), Index::Zero), ((0, 0), Index::Zero))]
    #[case(((0, 0), Index::Four), ((-1, 0), Index::One))]
    #[case(((0, 0), Index::Five), ((0, -1), Index::Two))]
    #[case(((-1, 0), Index::One), ((-1, 0), Index::One))]
    fn test_created_edge_coordinate_is_canonical(
        #[case] input: ((i8, i8), Index),
        #[case] expected: ((i8, i8), Index),
    ) {
        let ((q, r), edge) = input;
        let ((expected_q, expected_r), expected_edge) = expected;
        let edge = EdgeCoordinate::new(q, r, edge);
        assert_eq!(edge.q, expected_q);
        assert_eq!(edge.r, expected_r);
        assert_eq!(edge.index, expected_edge);
    }

    #[rstest]
    #[case(((0, 0), Index::Zero), ((0, -1), Index::Two))]
    #[case(((1, -1), Index::Four), ((0, -1), Index::Two))]
    #[case(((0, -1), Index::Two), ((0, -1), Index::Two))]
    #[case(((0, 0), Index::One), ((0, 0), Index::One))]
    #[case(((1, 0), Index::Five), ((0, 0), Index::One))]
    #[case(((1, -1), Index::Three), ((0, 0), Index::One))]
    #[case(((0, 0), Index::Two), ((0, 0), Index::Two))]
    #[case(((0, 1), Index::Zero), ((0, 0), Index::Two))]
    #[case(((1, 0), Index::Four), ((0, 0), Index::Two))]
    #[case(((0, 0), Index::Three), ((-1, 1), Index::One))]
    #[case(((-1, 1), Index::One), ((-1, 1), Index::One))]
    #[case(((0, 1), Index::Five), ((-1, 1), Index::One))]
    #[case(((0, 0), Index::Four), ((-1, 0), Index::Two))]
    #[case(((-1, 0), Index::Two), ((-1, 0), Index::Two))]
    #[case(((-1, 1), Index::Zero), ((-1, 0), Index::Two))]
    #[case(((0, 0), Index::Five), ((-1, 0), Index::One))]
    #[case(((0, -1), Index::Three), ((-1, 0), Index::One))]
    #[case(((-1, 0), Index::One), ((-1, 0), Index::One))]
    #[case(((2, -1), Index::Zero), ((2, -2), Index::Two))]
    #[case(((3, -2), Index::Four), ((2, -2), Index::Two))]
    #[case(((2, -2), Index::Two), ((2, -2), Index::Two))]
    fn test_created_vertex_coordinate_is_canonical(
        #[case] input: ((i8, i8), Index),
        #[case] expected: ((i8, i8), Index),
    ) {
        let ((q, r), vertex) = input;
        let ((expected_q, expected_r), expected_vertex) = expected;
        let vertex = VertexCoordinate::new(q, r, vertex);
        assert_eq!(vertex.q, expected_q);
        assert_eq!(vertex.r, expected_r);
        assert_eq!(vertex.index, expected_vertex);
    }

    #[test]
    fn edge_vertices_are_the_clockwise_endpoints() {
        let edge = EdgeCoordinate::new(0, 0, Index::Zero);
        assert_eq!(
            edge.vertices(),
            [
                VertexCoordinate::new(0, 0, Index::Zero),
                VertexCoordinate::new(0, 0, Index::One),
            ]
        );
    }

    #[test]
    fn vertex_hexes_match_across_aliases() {
        let canonical = VertexCoordinate::new(0, 0, Index::Zero);
        let mut expected = canonical.hexes();
        expected.sort_by_key(|hex| (hex.q, hex.r));
        assert_eq!(
            expected,
            [
                HexCoordinate { q: 0, r: -1 },
                HexCoordinate { q: 0, r: 0 },
                HexCoordinate { q: 1, r: -1 },
            ]
        );

        let raw = VertexCoordinate {
            q: 0,
            r: 0,
            index: Index::Zero,
        };
        let mut alias = raw.hexes();
        alias.sort_by_key(|hex| (hex.q, hex.r));
        assert_eq!(alias, expected);
    }
}

#[cfg(all(test, feature = "serde"))]
mod serde_tests {
    use super::Index;

    #[test]
    fn index_deserializes_from_python_number() {
        assert_eq!(serde_json::from_str::<Index>("0").unwrap(), Index::Zero);
        assert_eq!(serde_json::from_str::<Index>("5").unwrap(), Index::Five);
        assert!(serde_json::from_str::<Index>("6").is_err());
    }
}
