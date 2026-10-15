use super::*;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SourceOwnership {
    pub receipt: String,
    /// None means prepared, never permission to issue payload assignments.
    pub object: Option<String>,
}

impl Store {
    pub fn source_ownership(&self) -> Result<Option<SourceOwnership>> {
        self.call(|db| {
            Ok(db
                .connection
                .query_row(
                    "SELECT receipt,object FROM source_ownership WHERE singleton=1",
                    [],
                    |r| {
                        Ok(SourceOwnership {
                            receipt: r.get(0)?,
                            object: r.get(1)?,
                        })
                    },
                )
                .optional()?)
        })
    }

    /// Explicit first setup only. Existing enrollment, even without jobs, is
    /// legacy state and cannot be rebound by this operation.
    pub fn prepare_source_ownership(
        &self,
        path: &str,
        binding: &str,
        observation: &str,
        receipt: &str,
    ) -> Result<()> {
        if !(1..=8192).contains(&receipt.len())
            || !path.starts_with('/')
            || !(1..=4096).contains(&binding.len())
            || !(1..=2048).contains(&observation.len())
        {
            return Err(StoreError::InvalidContext);
        }
        let (path, binding, observation, receipt) = (
            path.to_owned(),
            binding.to_owned(),
            observation.to_owned(),
            receipt.to_owned(),
        );
        self.call(move |db| {
            let tx=db.connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
            let prior:Option<String>=tx.query_row("SELECT receipt FROM source_ownership WHERE singleton=1",[],|r|r.get(0)).optional()?;
            if let Some(prior)=prior {
                if prior!=receipt { return Err(StoreError::SourceRootChanged); }
                let matches:bool=tx.query_row("SELECT EXISTS(SELECT 1 FROM source_enrollment WHERE singleton=1 AND source_path=?1 AND binding=?2 AND observation=?3 AND state_instance_id=(SELECT value FROM metadata WHERE key='instance_id'))",params![path,binding,observation],|r|r.get(0))?;
                if !matches { return Err(StoreError::SourceRootChanged); }
            } else {
                let used:bool=tx.query_row("SELECT EXISTS(SELECT 1 FROM jobs) OR EXISTS(SELECT 1 FROM source_enrollment)",[],|r|r.get(0))?;
                if used { return Err(StoreError::SourceEnrollmentRequired); }
                tx.execute("INSERT INTO source_enrollment SELECT 1,?1,?2,?3,value FROM metadata WHERE key='instance_id'",params![path,binding,observation])?;
                tx.execute("INSERT INTO source_ownership VALUES(1,?1,NULL)",[receipt])?;
            }
            tx.commit()?;
            Ok(())
        })
    }

    pub fn activate_source_ownership(&self, receipt: &str, object: &str) -> Result<()> {
        if ObjectIdentity::decode(object).is_none() {
            return Err(StoreError::InvalidContext);
        }
        let (receipt, object) = (receipt.to_owned(), object.to_owned());
        self.call(move |db| {
            let changed=db.connection.execute("UPDATE source_ownership SET object=?2 WHERE singleton=1 AND receipt=?1 AND (object IS NULL OR object=?2)",params![receipt,object])?;
            if changed!=1 { return Err(StoreError::SourceRootChanged); }
            Ok(())
        })
    }
}
