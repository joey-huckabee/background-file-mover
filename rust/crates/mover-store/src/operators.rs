use super::*;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ResumeRequest {
    pub command_id: String,
    pub review_epoch: u32,
    pub actor: String,
    pub reason: String,
}
#[derive(Debug, PartialEq, Eq)]
pub struct ResumeReceipt {
    pub review_epoch: u32,
    pub replay: bool,
}
pub struct ResumeAudit {
    pub command_id: String,
    pub review_epoch: u32,
    pub actor: String,
    pub reason: String,
    pub recorded_at: i64,
    pub prior_retry_after: i64,
    pub prior_code: String,
}
pub(crate) fn latest(c: &Connection, id: i64) -> Result<Option<ResumeAudit>> {
    Ok(c.query_row("SELECT command_id,review_epoch,actor,reason,recorded_at,prior_retry_after,prior_code FROM operator_resumes WHERE job_id=?1 ORDER BY review_epoch DESC LIMIT 1",[id],|r|Ok(ResumeAudit{command_id:r.get(0)?,review_epoch:r.get(1)?,actor:r.get(2)?,reason:r.get(3)?,recorded_at:r.get(4)?,prior_retry_after:r.get(5)?,prior_code:r.get(6)?})).optional()?)
}
pub(crate) fn epoch(c: &Connection, id: i64) -> Result<u32> {
    Ok(c.query_row(
        "SELECT count(*) FROM operator_resumes WHERE job_id=?1",
        [id],
        |r| r.get(0),
    )?)
}
impl Store {
    /// Request reconciliation, never authorize a filesystem effect directly.
    pub fn resume_delivery(
        &self,
        id: i64,
        request: &ResumeRequest,
        now: i64,
    ) -> Result<ResumeReceipt> {
        let request = request.clone();
        self.call(move |db| {
            let valid = |s: &str, max: usize| !s.trim().is_empty() && s.len()<=max && !s.chars().any(char::is_control);
            if now<0 || !valid(&request.command_id,128) || !valid(&request.actor,128) || !valid(&request.reason,512) {
                return Err(StoreError::InvalidContext);
            }
            let tx = db.connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
            let prior: Option<(u32,String,String)> = tx.query_row("SELECT review_epoch,actor,reason FROM operator_resumes WHERE job_id=?1 AND command_id=?2",params![id,request.command_id],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?))).optional()?;
            if let Some((review_epoch,actor,reason)) = prior {
                if review_epoch!=request.review_epoch || actor!=request.actor || reason!=request.reason {return Err(StoreError::ActionConflict);}
                tx.commit()?;
                return Ok(ResumeReceipt{review_epoch:review_epoch+1,replay:true});
            }
            let job = load(&tx,id)?.ok_or(StoreError::NotFound)?;
            if job.recording.handoff()!=mover_core::Handoff::Ready202 || job.recording.is_committed() {return Err(StoreError::ReviewConflict);}
            let current_epoch = epoch(&tx,id)?;
            if current_epoch>=64 {return Err(StoreError::AuditFull);}
            if current_epoch!=request.review_epoch {return Err(StoreError::ReviewConflict);}
            let failure: Option<(u32,i64,String)> = tx.query_row("SELECT failures,retry_after,code FROM delivery_failures WHERE job_id=?1",[id],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?))).optional()?;
            let Some((3,retry_after,code)) = failure else {return Err(StoreError::ReviewConflict);};
            tx.execute("INSERT INTO operator_resumes VALUES(?1,?2,?3,?4,?5,?6,?7,?8)",params![id,request.command_id,current_epoch,request.actor,request.reason,now,retry_after,code])?;
            tx.execute("DELETE FROM delivery_failures WHERE job_id=?1",[id])?;
            tx.commit()?;
            Ok(ResumeReceipt{review_epoch:current_epoch+1,replay:false})
        })
    }
}
