use super::*;

#[derive(Clone)]
pub struct MissingResetRequest {
    pub command_id: String,
    pub review_epoch: u32,
    pub file_index: u32,
    pub retry_window_seconds: u32,
    pub actor: String,
    pub reason: String,
}
pub struct MissingResetReceipt {
    pub review_epoch: u32,
    pub new_deadline: i64,
    pub replay: bool,
}
pub struct MissingResetAudit {
    pub request: MissingResetRequest,
    pub recorded_at: i64,
    pub prior_deadline: i64,
    pub prior_blocked: bool,
    pub new_deadline: i64,
}
pub(crate) fn epoch(c: &Connection, id: i64) -> Result<u32> {
    Ok(c.query_row(
        "SELECT count(*) FROM missing_resets WHERE job_id=?1",
        [id],
        |r| r.get(0),
    )?)
}
fn audit(r: &rusqlite::Row<'_>) -> rusqlite::Result<MissingResetAudit> {
    Ok(MissingResetAudit {
        request: MissingResetRequest {
            command_id: r.get(0)?,
            review_epoch: r.get(1)?,
            file_index: r.get(2)?,
            retry_window_seconds: r.get(3)?,
            actor: r.get(4)?,
            reason: r.get(5)?,
        },
        recorded_at: r.get(6)?,
        prior_deadline: r.get(7)?,
        prior_blocked: r.get(8)?,
        new_deadline: r.get(9)?,
    })
}
pub(crate) fn latest(c: &Connection, id: i64) -> Result<Option<MissingResetAudit>> {
    Ok(c.query_row("SELECT command_id,review_epoch,file_index,retry_window_seconds,actor,reason,recorded_at,prior_deadline,prior_blocked,new_deadline FROM missing_resets WHERE job_id=?1 ORDER BY review_epoch DESC LIMIT 1",[id],audit).optional()?)
}
impl Store {
    /// Extend only an explicitly reviewed pending file's missing deadline.
    /// No claim intent, receipt, reservation, route or filesystem object changes.
    pub fn reset_missing(
        &self,
        id: i64,
        request: &MissingResetRequest,
        now: i64,
    ) -> Result<MissingResetReceipt> {
        let request = request.clone();
        self.call(move |db| {
            let valid=|s:&str,max:usize|!s.trim().is_empty() && s.len()<=max && !s.chars().any(char::is_control);
            if now<0 || !valid(&request.command_id,128) || !valid(&request.actor,128) || !valid(&request.reason,512) || !(1..=86400).contains(&request.retry_window_seconds) {
                return Err(StoreError::InvalidContext);
            }
            let tx=db.connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
            let prior=tx.query_row("SELECT command_id,review_epoch,file_index,retry_window_seconds,actor,reason,recorded_at,prior_deadline,prior_blocked,new_deadline FROM missing_resets WHERE job_id=?1 AND command_id=?2",params![id,request.command_id],audit).optional()?;
            if let Some(p)=prior {
                let r=&p.request;
                if r.review_epoch!=request.review_epoch || r.file_index!=request.file_index || r.retry_window_seconds!=request.retry_window_seconds || r.actor!=request.actor || r.reason!=request.reason {return Err(StoreError::ActionConflict);}
                tx.commit()?;
                return Ok(MissingResetReceipt{review_epoch:r.review_epoch+1,new_deadline:p.new_deadline,replay:true});
            }
            let job=load(&tx,id)?.ok_or(StoreError::NotFound)?;
            if job.recording.file_phase(request.file_index as usize)!=Some(mover_core::FilePhase::Pending) {return Err(StoreError::ReviewConflict);}
            let current_epoch=epoch(&tx,id)?;
            if current_epoch>=64 {return Err(StoreError::AuditFull);}
            if current_epoch!=request.review_epoch {return Err(StoreError::ReviewConflict);}
            let missing:Option<(i64,bool)>=tx.query_row("SELECT deadline,blocked FROM missing WHERE job_id=?1 AND file_index=?2",params![id,request.file_index],|r|Ok((r.get(0)?,r.get(1)?))).optional()?;
            let Some((deadline,blocked))=missing else {return Err(StoreError::ReviewConflict);};
            if !blocked && deadline>now {return Err(StoreError::ReviewConflict);}
            let new_deadline=now.checked_add(i64::from(request.retry_window_seconds)).ok_or(StoreError::InvalidContext)?;
            tx.execute("INSERT INTO missing_resets VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11)",params![id,request.command_id,current_epoch,request.file_index,request.actor,request.reason,now,deadline,blocked,new_deadline,request.retry_window_seconds])?;
            tx.execute("UPDATE missing SET deadline=?1,blocked=0 WHERE job_id=?2 AND file_index=?3",params![new_deadline,id,request.file_index])?;
            tx.commit()?;
            Ok(MissingResetReceipt{review_epoch:current_epoch+1,new_deadline,replay:false})
        })
    }
}
