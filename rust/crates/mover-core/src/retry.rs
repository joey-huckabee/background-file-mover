//! Failure classification selects scheduling only, never filesystem authority.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DeliveryFailureKind {
    Unclassified,
    DestinationCapacity,
}
impl DeliveryFailureKind {
    pub fn code(self) -> &'static str {
        match self {
            Self::Unclassified => "delivery_requires_review",
            Self::DestinationCapacity => "destination_capacity_requires_review",
        }
    }
    /// Delays after total persisted failures 1, 2, 3. Three failures still require review.
    pub fn delays(self) -> [i64; 3] {
        match self {
            Self::Unclassified => [5, 5, 5],
            Self::DestinationCapacity => [30, 60, 120],
        }
    }
}
