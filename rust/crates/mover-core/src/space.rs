//! Pure available-space decision; existing payload is already on the filesystem.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SpaceStatistics {
    pub available_blocks: u64,
    pub total_blocks: u64,
    pub fragment_size: u64,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SpaceDecision {
    pub available_bytes: u128,
    pub required_bytes: u128,
    pub sufficient: bool,
}
impl SpaceStatistics {
    pub fn decide(self, min_bytes: u64, percent: u8) -> Option<SpaceDecision> {
        if self.fragment_size == 0
            || self.total_blocks == 0
            || self.available_blocks > self.total_blocks
            || percent > 100
        {
            return None;
        }
        let available_bytes = u128::from(self.available_blocks) * u128::from(self.fragment_size);
        let total = u128::from(self.total_blocks) * u128::from(self.fragment_size);
        let percent = u128::from(percent);
        let floor = (total / 100)
            .checked_mul(percent)?
            .checked_add(((total % 100) * percent).div_ceil(100))?;
        let required_bytes = u128::from(min_bytes).max(floor);
        Some(SpaceDecision {
            available_bytes,
            required_bytes,
            sufficient: available_bytes >= required_bytes,
        })
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn space_thresholds_round_up_without_double_charging_or_overflow() {
        let s = SpaceStatistics {
            available_blocks: 150,
            total_blocks: 1000,
            fragment_size: 1,
        };
        assert!(s.decide(150, 0).unwrap().sufficient);
        assert!(!s.decide(151, 0).unwrap().sufficient);
        assert_eq!(s.decide(100, 20).unwrap().required_bytes, 200);
        assert!(!s.decide(100, 20).unwrap().sufficient);
        let s = SpaceStatistics {
            total_blocks: 101,
            available_blocks: 6,
            fragment_size: 1,
        };
        assert!(s.decide(0, 5).unwrap().sufficient);
        assert_eq!(s.decide(0, 5).unwrap().required_bytes, 6);
        assert!(
            !SpaceStatistics {
                available_blocks: 5,
                ..s
            }
            .decide(0, 5)
            .unwrap()
            .sufficient
        );
        let large = SpaceStatistics {
            total_blocks: u64::MAX,
            available_blocks: u64::MAX,
            fragment_size: u64::MAX,
        };
        assert!(large.decide(u64::MAX, 100).unwrap().sufficient);
        assert!(
            !SpaceStatistics {
                available_blocks: 0,
                ..s
            }
            .decide(1, 0)
            .unwrap()
            .sufficient
        );
        assert!(
            SpaceStatistics {
                fragment_size: 0,
                ..s
            }
            .decide(1, 0)
            .is_none()
        );
        assert!(
            SpaceStatistics {
                total_blocks: 0,
                ..s
            }
            .decide(1, 0)
            .is_none()
        );
        assert!(
            SpaceStatistics {
                available_blocks: 102,
                ..s
            }
            .decide(1, 0)
            .is_none()
        );
        assert!(s.decide(1, 101).is_none());
    }
}
