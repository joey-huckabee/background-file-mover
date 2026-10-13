use super::*;

/// Conservative database reservations, not physical usage or custody evidence.
pub struct RetentionSnapshot {
    pub job_id: Option<i64>,
    pub jobs: u64,
    pub committed_jobs: u64,
    pub source_claims: u64,
    pub confirmed_claims: u64,
    pub unmeasured_files: u64,
    pub source_reserved_bytes: u128,
    pub destination_reserved_bytes: u128,
    pub destination_attempts_by_phase: [u64; 5],
    pub configured_limits: Option<(u64, u64)>,
}
pub(crate) fn reserved_bytes(c: &Connection, destination: bool, id: Option<i64>) -> Result<u128> {
    let sql = if destination {
        "SELECT c.source_identity FROM transfers t JOIN claims c ON c.job_id=t.job_id AND c.file_index=t.file_index WHERE (?1 IS NULL OR t.job_id=?1)"
    } else {
        "SELECT source_identity FROM claims WHERE (?1 IS NULL OR job_id=?1)"
    };
    let mut s = c.prepare(sql)?;
    let mut total = 0_u128;
    for row in s.query_map([id], |r| r.get::<_, String>(0))? {
        let size = ObjectIdentity::decode(&row?)
            .ok_or(StoreError::CorruptState)?
            .size;
        total = total
            .checked_add(u128::from(size))
            .ok_or(StoreError::CorruptState)?;
    }
    Ok(total)
}
impl Store {
    /// Stream a constant-sized report from one read transaction. No FS effects.
    pub fn retention(&self, id: Option<i64>) -> Result<Option<RetentionSnapshot>> {
        self.call(move|db| {
            let tx=db.connection.transaction()?;
            let count=|sql:&str|->Result<u64> {
                let n:i64=tx.query_row(sql,[id],|r|r.get(0))?;
                u64::try_from(n).map_err(|_|StoreError::CorruptState)
            };
            let jobs=count("SELECT count(*) FROM jobs WHERE (?1 IS NULL OR job_id=?1)")?;
            if id.is_some() && jobs==0 {return Ok(None);}
            let committed_jobs=count("SELECT count(*) FROM manifests WHERE phase=4 AND (?1 IS NULL OR job_id=?1)")?;
            let source_claims=count("SELECT count(*) FROM claims WHERE (?1 IS NULL OR job_id=?1)")?;
            let confirmed_claims=count("SELECT count(*) FROM claims WHERE done=1 AND (?1 IS NULL OR job_id=?1)")?;
            let unmeasured_files=count("SELECT count(*) FROM files f LEFT JOIN claims c ON c.job_id=f.job_id AND c.file_index=f.file_index WHERE c.job_id IS NULL AND (?1 IS NULL OR f.job_id=?1)")?;
            let source_reserved_bytes=reserved_bytes(&tx,false,id)?;
            let destination_reserved_bytes=reserved_bytes(&tx,true,id)?;
            let mut destination_attempts_by_phase=[0;5];
            {
                let mut s=tx.prepare("SELECT phase,count(*) FROM transfers WHERE (?1 IS NULL OR job_id=?1) GROUP BY phase")?;
                for row in s.query_map([id],|r|Ok((r.get::<_,i64>(0)?,r.get::<_,i64>(1)?)))? {
                    let (phase,n)=row?;
                    let slot=usize::try_from(phase).ok().and_then(|i|destination_attempts_by_phase.get_mut(i)).ok_or(StoreError::CorruptState)?;
                    *slot=u64::try_from(n).map_err(|_|StoreError::CorruptState)?;
                }
            }
            tx.commit()?;
            Ok(Some(RetentionSnapshot{job_id:id,jobs,committed_jobs,source_claims,confirmed_claims,unmeasured_files,source_reserved_bytes,destination_reserved_bytes,destination_attempts_by_phase,configured_limits:db.limits}))
        })
    }
}
