//! Last recorded problem per job (schema 14): the bounded, path-free worker
//! diagnostic behind a claim or delivery failure, so an operator can see what to
//! fix. Informational only: never an effect receipt, retry authorization or
//! custody fact. Replaced by each new problem; removed with the job's history.
use super::*;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ProblemStage {
    Claim,
    Delivery,
}
impl ProblemStage {
    fn as_str(self) -> &'static str {
        match self {
            Self::Claim => "claim",
            Self::Delivery => "delivery",
        }
    }
    fn parse(s: &str) -> Result<Self> {
        match s {
            "claim" => Ok(Self::Claim),
            "delivery" => Ok(Self::Delivery),
            _ => Err(StoreError::CorruptState),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct JobProblem {
    pub stage: ProblemStage,
    /// Printable ASCII, at most 240 bytes; never contains paths or payload.
    pub diagnostic: String,
    pub file_index: Option<usize>,
    pub recorded_at: i64,
}

/// Same bound the worker protocol enforces before a diagnostic is accepted.
pub fn valid_diagnostic(text: &str) -> bool {
    (1..=240).contains(&text.len()) && text.bytes().all(|c| c.is_ascii_graphic() || c == b' ')
}

pub(super) fn latest(tx: &rusqlite::Transaction<'_>, job_id: i64) -> Result<Option<JobProblem>> {
    let row: Option<(String, String, Option<i64>, i64)> = tx
        .query_row(
            "SELECT stage,diagnostic,file_index,recorded_at FROM job_problems WHERE job_id=?1",
            [job_id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
        )
        .optional()?;
    row.map(|(stage, diagnostic, file_index, recorded_at)| {
        Ok(JobProblem {
            stage: ProblemStage::parse(&stage)?,
            diagnostic,
            file_index: file_index.map(|i| i as usize),
            recorded_at,
        })
    })
    .transpose()
}

impl Store {
    /// Record (replace) the job's latest problem. Missing jobs are ignored; an
    /// invalid diagnostic is refused rather than stored.
    pub fn record_problem(
        &self,
        job_id: i64,
        stage: ProblemStage,
        diagnostic: &str,
        file_index: Option<usize>,
        now: i64,
    ) -> Result<()> {
        if now < 0 || !valid_diagnostic(diagnostic) || file_index.is_some_and(|i| i > 255) {
            return Err(StoreError::InvalidContext);
        }
        let diagnostic = diagnostic.to_owned();
        self.call(move |db| {
            db.connection.execute(
                "INSERT INTO job_problems SELECT ?1,?2,?3,?4,?5 WHERE EXISTS(SELECT 1 FROM jobs WHERE job_id=?1) \
                 ON CONFLICT(job_id) DO UPDATE SET stage=excluded.stage,diagnostic=excluded.diagnostic,\
                 file_index=excluded.file_index,recorded_at=excluded.recorded_at",
                params![
                    job_id,
                    stage.as_str(),
                    diagnostic,
                    file_index.map(|i| i as i64),
                    now
                ],
            )?;
            Ok(())
        })
    }
}
