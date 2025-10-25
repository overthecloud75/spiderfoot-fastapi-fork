# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfdb
# Purpose:      Common functions for working with the database back-end.
#
# Author:      Steve Micallef <steve@binarypool.com>
#
# Created:     15/05/2012
# Copyright:   (c) Steve Micallef 2012
# Licence:     MIT
# -------------------------------------------------------------------------------

from pathlib import Path
import hashlib
import random
import re
import threading
import time
from sqlalchemy import create_engine, event, func, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker

from .db_config import DATABASE_URL, EVENT_DETAILS
from models import Base, Config, ScanConfig, EventTypes, ScanInstance, ScanLog, ScanResults, ScanCorrelationResults, ScanCorrelationResultsEvents


class SpiderFootDb:
    """SpiderFoot database

    Attributes:
        conn: SQLite connect() connection
        dbh: SQLite cursor() database handle
        dbhLock (_thread.RLock): thread lock on database handle
    """

    dbh = None
    conn = None

    # Prevent multithread access to sqlite database
    dbhLock = threading.RLock()

    def __init__(self, init: bool = False) -> None:
        """Initialize database and create handle to the SQLite database file.
        Creates the database file if it does not exist.
        Creates database schema if it does not exist.

        Args:
            init (bool): initialise the database schema.
                         if the database file does not exist this option will be ignored.

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
            IOError: database I/O failed
        """
        try:
            # Engine 생성
            self.engine = create_engine(
                DATABASE_URL,
                connect_args={"check_same_thread": False}  # SQLite는 멀티스레드 사용 시 필요
            )
        except Exception as e:
            raise IOError(f"Error connecting to internal database {database_path}") from e

        # 세션 생성기
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        # 실제 세션 생성
        self.dbh = SessionLocal()

        def __dbregex__(qry: str, data: str) -> bool:
            """SQLite doesn't support regex queries, so we create
            a custom function to do so.

            Args:
                qry (str): TBD
                data (str): TBD

            Returns:
                bool: matches
            """

            try:
                rx = re.compile(qry, re.IGNORECASE | re.DOTALL)
                ret = rx.match(data)
            except Exception:
                return False
            return ret is not None

        # Now we actually check to ensure the database file has the schema set
        # up correctly.
        with self.dbhLock:
            try:
                self.dbh.query(func.count()).select_from(ScanConfig).scalar()
                @event.listens_for(self.dbh.bind, "connect")
                def register_regex(dbapi_connection, connection_record):
                    dbapi_connection.create_function("REGEXP", 2, __dbregex__)
            except SQLAlchemyError as e:
                init = True
                try:
                    self.create() 
                except Exception as inner_e:
                    raise IOError("Tried to set up the SpiderFoot database schema, but failed") from inner_e

    def create(self) -> None:
        """Create the database schema.

        Raises:
            IOError: database I/O failed
        """

        with self.dbhLock:
            try:
                # 1️⃣ 테이블 생성
                Base.metadata.create_all(bind=self.engine)

                # 2️⃣ 초기 데이터 삽입
                for row in EVENT_DETAILS:
                    event, event_descr, event_raw, event_type = row
                    evt = EventTypes(
                        event=event,
                        event_descr=event_descr,
                        event_raw=event_raw,
                        event_type=event_type
                    )
                    self.dbh.add(evt)
                self.dbh.commit()  # 모든 추가를 한 번에 커밋

            except SQLAlchemyError as e:
                self.dbh.rollback()  
                raise IOError("SQL error encountered when setting up database") from e

    def close(self) -> None:
        """Close the database handle."""

        with self.dbhLock:
            self.dbh.close()

    def vacuumDB(self) -> None:
        """Vacuum the database. Clears unused database file pages.

        Returns:
            bool: success

        Raises:
            IOError: database I/O failed
        """
        with self.dbhLock:
            try:
                self.dbh.execute(text("VACUUM"))
                self.dbh.commit()
                return True
            except SQLAlchemyError as e:
                raise IOError("SQL error encountered when vacuuming the database") from e
        return False

    def search(self, criteria: dict, filterFp: bool = False) -> list:
        """Search database.

        Args:
            criteria (dict): search criteria such as:
                - scan_id (search within a scan, if omitted search all)
                - type (search a specific type, if omitted search all)
                - value (search values for a specific string, if omitted search all)
                - regex (search values for a regular expression)
                ** at least two criteria must be set **
            filterFp (bool): filter out false positives

        Returns:
            list: search results

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
            IOError: database I/O failed
        """
        if not isinstance(criteria, dict):
            raise TypeError(f"criteria is {type(criteria)}; expected dict") from None

        valid_criteria = ['scan_id', 'type', 'value', 'regex']

        for key in list(criteria.keys()):
            if key not in valid_criteria:
                criteria.pop(key, None)
                continue

            if not isinstance(criteria.get(key), str):
                raise TypeError(f"criteria[{key}] is {type(criteria.get(key))}; expected str()") from None

            if not criteria[key]:
                criteria.pop(key, None)
                continue

        if len(criteria) == 0:
            raise ValueError(f"No valid search criteria provided; expected: {', '.join(valid_criteria)}") from None

        if len(criteria) == 1:
            raise ValueError("Only one search criteria provided; expected at least two")

        params = {}
        qry_str = """
            SELECT ROUND(c.generated) AS generated, 
                c.data, 
                s.data as 'source_data', 
                c.module, 
                c.type, 
                c.confidence, 
                c.visibility, 
                c.risk, 
                c.hash,
                c.source_event_hash, 
                t.event_descr, 
                t.event_type, 
                c.scan_instance_id,
                c.false_positive as 'fp', 
                s.false_positive as 'parent_fp'
            FROM tbl_scan_results c, 
                tbl_scan_results s, 
                tbl_event_types t
            WHERE s.scan_instance_id = c.scan_instance_id 
                AND t.event = c.type 
                AND c.source_event_hash = s.hash 
        """

        if filterFp:
            qry_str += " AND c.false_positive <> 1 "

        if criteria.get('scan_id') is not None:
            qry_str += "AND c.scan_instance_id = :scan_id "
            params['scan_id'] = criteria['scan_id']

        if criteria.get('type') is not None:
            qry_str += " AND c.type = :type "
            params['type'] = criteria['type']

        if criteria.get('value') is not None:
            qry_str += " AND (c.data LIKE :value OR s.data LIKE :value) "
            params['value'] = criteria['value']

        if criteria.get('regex') is not None:
            qry_str += " AND (c.data REGEXP :regex OR s.data REGEXP :regex) "
            params['regex'] = criteria['regex']

        qry_str += " ORDER BY c.data"

        with self.dbhLock:
            try:
                result = self.dbh.execute(qry, params)
                return result.fetchall()
            except SQLAlchemyError as e:
                raise IOError("SQL error encountered when fetching search results") from e

    def eventTypes(self) -> list:
        """Get event types.

        Returns:
            list: event types

        Raises:
            IOError: database I/O failed
        """
        with self.dbhLock:
            try:
                results = self.dbh.query(EventTypes).all()
                data = [[r.event_descr, r.event, r.event_raw, r.event_type] for r in results]
                return data
            except Exception as e:
                raise IOError("SQL error encountered when retrieving event types") from e

    def scanLogEvents(self, batch: list) -> bool:
        """Logs a batch of events to the database.

        Args:
            batch (list): tuples containing: instanceId, classification, message, component, logTime

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed

        Returns:
            bool: Whether the logging operation succeeded
        """

        log_entries = []

        for instanceId, classification, message, component, logTime in batch:
            if not isinstance(instanceId, str):
                raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

            if not isinstance(classification, str):
                raise TypeError(f"classification is {type(classification)}; expected str()") from None

            if not isinstance(message, str):
                raise TypeError(f"message is {type(message)}; expected str()") from None

            if not component:
                component = "SpiderFoot"

            # logTime은 초 단위라면 ms로 변환
            log_entries.append(
                ScanLog(
                    scan_instance_id=instanceId,
                    generated=logTime * 1000,
                    component=component,
                    type=classification,
                    message=message
                )
            )

        if not log_entries:
            return True

        with self.dbhLock:
            try:
                self.dbh.add_all(log_entries)  # ✅ bulk insert
                self.dbh.commit()
            except SQLAlchemyError as e:
                err_msg = str(e).lower()
                if "locked" not in err_msg and "thread" not in err_msg:
                    self.dbh.rollback()
                    raise IOError("Unable to log scan event in database") from e
                return False
        return True

    def scanLogEvent(self, instanceId: str, classification: str, message: str, component: str = None) -> None:
        """Log an event to the database.

        Args:
            instanceId (str): scan instance ID
            classification (str): TBD
            message (str): TBD
            component (str): TBD

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed

        Todo:
            Do something smarter to handle database locks
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(classification, str):
            raise TypeError(f"classification is {type(classification)}; expected str()") from None

        if not isinstance(message, str):
            raise TypeError(f"message is {type(message)}; expected str()") from None

        if not component:
            component = "SpiderFoot"

        event = ScanLog(
            scan_instance_id=instanceId,
            generated=time.time() * 1000,
            component=component,
            type=classification,
            message=message
        )

        with self.dbhLock:
            try:
                self.dbh.add(event)
                self.dbh.commit()

            except SQLAlchemyError as e:
                if "locked" not in str(e) and "thread" not in str(e):
                    raise IOError("Unable to log scan event in database") from e
                pass

    def scanInstanceCreate(self, instanceId: str, scanName: str, scanTarget: str) -> None:
        """Store a scan instance in the database.

        Args:
            instanceId (str): scan instance ID
            scanName(str): scan name
            scanTarget (str): scan target

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(scanName, str):
            raise TypeError(f"scanName is {type(scanName)}; expected str()") from None

        if not isinstance(scanTarget, str):
            raise TypeError(f"scanTarget is {type(scanTarget)}; expected str()") from None

        new_instance = ScanInstance(
            guid=instanceId,
            name=scanName,
            seed_target=scanTarget,
            created=time.time() * 1000,
            status='CREATED'
        )

        with self.dbhLock:
            try:
                self.dbh.add(new_instance)
                self.dbh.commit()
            except SQLAlchemyError as e:
                if "locked" not in str(e) and "thread" not in str(e):
                    raise IOError("Unable to log scan event in database") from e
                pass

    def scanInstanceSet(self, instanceId: str, started: str = None, ended: str = None, status: str = None) -> None:
        """Update the start time, end time or status (or all 3) of a scan instance.

        Args:
            instanceId (str): scan instance ID
            started (str): scan start time
            ended (str): scan end time
            status (str): scan status

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        update_dict = {}
        if started is not None:
            update_dict["started"] = started
        if ended is not None:
            update_dict["ended"] = ended
        if status is not None:
            update_dict["status"] = status

        if not update_dict:
            return

        with self.dbhLock:
            try:
                self.dbh.query(ScanInstance).filter(
                    ScanInstance.guid == instanceId
                ).update(update_dict, synchronize_session=False)
                self.dbh.commit()
            except SQLAlchemyError:
                raise IOError("Unable to set information for the scan instance.") from None

    def scanInstanceGet(self, instanceId: str) -> list:
        """Return info about a scan instance (name, target, created, started, ended, status)

        Args:
            instanceId (str): scan instance ID

        Returns:
            list: scan instance info

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        with self.dbhLock:
            try:
                # ORM 쿼리
                row = self.dbh.query(
                    ScanInstance.name,
                    ScanInstance.seed_target,
                    (ScanInstance.created / 1000).label("created"),
                    (ScanInstance.started / 1000).label("started"),
                    (ScanInstance.ended / 1000).label("ended"),
                    ScanInstance.status
                ).filter(
                    ScanInstance.guid == instanceId
                ).one_or_none()

                if row is None:
                    return None

                return [row.name, row.seed_target, int(row.created), int(row.started), int(row.ended), row.status]

            except SQLAlchemyError as e:
                raise IOError("SQL error encountered when retrieving scan instance") from e

    def scanResultSummary(self, instanceId: str, by: str = "type") -> list:
        """Obtain a summary of the results, filtered by event type, module or entity.

        Args:
            instanceId (str): scan instance ID
            by (str): filter by type

        Returns:
            list: scan instance info

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(by, str):
            raise TypeError(f"by is {type(by)}; expected str()") from None

        if by not in ["type", "module", "entity"]:
            raise ValueError(f"Invalid filter by value: {by}") from None

        if by == "type":
            qry = text("""
                SELECT r.type, e.event_descr, MAX(ROUND(generated)) AS last_in,
                    COUNT(*) AS total, COUNT(DISTINCT r.data) AS utotal
                FROM tbl_scan_results r
                JOIN tbl_event_types e ON e.event = r.type
                WHERE r.scan_instance_id = :instance_id
                GROUP BY r.type
                ORDER BY e.event_descr
            """)
        elif by == "module":
            qry = text("""
                SELECT r.module, '' AS event_descr, MAX(ROUND(generated)) AS last_in,
                    COUNT(*) AS total, COUNT(DISTINCT r.data) AS utotal
                FROM tbl_scan_results r
                JOIN tbl_event_types e ON e.event = r.type
                WHERE r.scan_instance_id = :instance_id
                GROUP BY r.module
                ORDER BY r.module DESC
            """)
        elif by == "entity":
            qry = text("""
                SELECT r.data, e.event_descr, MAX(ROUND(generated)) AS last_in,
                    COUNT(*) AS total, COUNT(DISTINCT r.data) AS utotal
                FROM tbl_scan_results r
                JOIN tbl_event_types e ON e.event = r.type
                WHERE r.scan_instance_id = :instance_id
                AND e.event_type IN ('ENTITY')
                GROUP BY r.data, e.event_descr
                ORDER BY total DESC
                LIMIT 50
            """)

        with self.dbhLock:
            try:
                result = self.dbh.execute(qry, {"instance_id": instanceId})
                return result.fetchall()
            except Exception as e:
                raise IOError("SQL error encountered when fetching result summary") from e

    def scanCorrelationSummary(self, instanceId: str, by: str = "rule") -> list:
        """Obtain a summary of the correlations, filtered by rule or risk

        Args:
            instanceId (str): scan instance ID
            by (str): filter by rule or risk

        Returns:
            list: scan correlation summary

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(by, str):
            raise TypeError(f"by is {type(by)}; expected str()") from None

        if by not in ["risk", "rule"]:
            raise ValueError(f"Invalid filter by value: {by}") from None

        if by == "risk":
            qry = text("""
                SELECT rule_risk, COUNT(*) AS total
                FROM tbl_scan_correlation_results
                WHERE scan_instance_id = :instance_id
                GROUP BY rule_risk
                ORDER BY rule_id
            """)
        elif by == "rule":
            qry = text("""
                SELECT rule_id, rule_name, rule_risk, rule_descr,
                    COUNT(*) AS total
                FROM tbl_scan_correlation_results
                WHERE scan_instance_id = :instance_id
                GROUP BY rule_id
                ORDER BY rule_id
            """)

        with self.dbhLock:
            try:
                result = self.dbh.execute(qry, {"instance_id": instanceId})
                return result.fetchall()
            except Exception as e:
                raise IOError("SQL error encountered when fetching correlation summary") from e

    def scanCorrelationList(self, instanceId: str) -> list:
        """Obtain a list of the correlations from a scan

        Args:
            instanceId (str): scan instance ID

        Returns:
            list: scan correlation list

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        qry = text("""
            SELECT c.id, c.title, c.rule_id, c.rule_risk, c.rule_name,
                c.rule_descr, c.rule_logic, COUNT(e.event_hash) AS event_count
            FROM tbl_scan_correlation_results c
            JOIN tbl_scan_correlation_results_events e
            ON c.id = e.correlation_id
            WHERE c.scan_instance_id = :instance_id
            GROUP BY c.id
            ORDER BY c.title, c.rule_risk
        """)

        with self.dbhLock:
            try:
                result = self.dbh.execute(qry, {"instance_id": instanceId})
                return result.fetchall()
            except Exception as e:
                raise IOError("SQL error encountered when fetching correlation list") from e

    def scanResultEvent(
        self,
        instanceId: str,
        eventType: str = 'ALL',
        srcModule: str = None,
        data: list = None,
        sourceId: list = None,
        correlationId: str = None,
        filterFp: bool = False
    ) -> list:
        """Obtain the data for a scan and event type.

        Args:
            instanceId (str): scan instance ID
            eventType (str): filter by event type
            srcModule (str): filter by the generating module
            data (list): filter by the data
            sourceId (list): filter by the ID of the source event
            correlationId (str): filter by the ID of a correlation result
            filterFp (bool): filter false positives

        Returns:
            list: scan results

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(eventType, str) and not isinstance(eventType, list):
            raise TypeError(f"eventType is {type(eventType)}; expected str() or list") from None

        qry_str = """
            SELECT ROUND(c.generated) AS generated, c.data, s.data as 'source_data', 
                c.module, c.type, c.confidence, c.visibility, c.risk, c.hash, 
                c.source_event_hash, t.event_descr, t.event_type, s.scan_instance_id, 
                c.false_positive as 'fp', s.false_positive as 'parent_fp' 
            FROM tbl_scan_results c, tbl_scan_results s, tbl_event_types t 
        """

        if correlationId:
            qry_str += ", tbl_scan_correlation_results_events ce "

        qry_str += "WHERE c.scan_instance_id = :instance_id AND c.source_event_hash = s.hash AND s.scan_instance_id = c.scan_instance_id AND t.event = c.type"

        params = {}
        params["instance_id"] = instanceId

        if correlationId:
            qry_str += " AND ce.event_hash = c.hash AND ce.correlation_id = :correlation_id"
            params["correlation_id"] = correlationId

        if eventType != "ALL":
            if isinstance(eventType, list):
                placeholders = ", ".join([f":event_type{i}" for i in range(len(eventType))])
                qry_str += f" AND c.type IN ({placeholders})"

                # 파라미터 딕셔너리 생성
                for i, t in enumerate(eventType):
                    params[f"event_type{i}"] = t
            else:
                qry_str += " AND c.type = :event_type"
                params["event_type"] = eventType

        if filterFp:
            qry_str += " AND c.false_positive <> 1"

        if srcModule:
            if isinstance(srcModule, list):
                placeholders = ", ".join([f":src_module{i}" for i in range(len(srcModule))])
                qry_str += f" AND c.module IN ({placeholders})"

                # 파라미터 딕셔너리 생성
                for i, m in enumerate(srcModule):
                    params[f"src_module{i}"] = m
            else:
                qry += " AND c.module = :src_module"
                params["src_module"] = srcModule

        if data:
            if isinstance(data, list):
                placeholders = ", ".join([f":data{i}" for i in range(len(data))])
                qry_str += f" AND c.data IN ({placeholders})"

                # 파라미터 딕셔너리 생성
                for i, d in enumerate(data):
                    params[f"data{i}"] = d
            else:
                qry_str += " AND c.data = :data"
                params["data"] = data

        if sourceId:
            if isinstance(sourceId, list):
                placeholders = ", ".join([f":source_id{i}" for i in range(len(sourceId))])
                qry_str += f" AND c.source_event_hash IN ({placeholders})"

                # 파라미터 딕셔너리 생성
                for i, s in enumerate(sourceId):
                    params[f"source_id{i}"] = s
            else:
                qry_str += " AND c.source_event_hash = :source_id"
                params["source_id"] = sourceId

        qry_str += " ORDER BY c.data"

        with self.dbhLock:
            try:
                result = self.dbh.execute(text(qry_str), params)
                return result.fetchall()
            except Exception as e:
                raise IOError("SQL error encountered when fetching result events") from e

    def scanResultEventUnique(self, instanceId: str, eventType: str = 'ALL', filterFp: bool = False) -> list:
        """Obtain a unique list of elements.

        Args:
            instanceId (str): scan instance ID
            eventType (str): filter by event type
            filterFp (bool): filter false positives

        Returns:
            list: unique scan results

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(eventType, str):
            raise TypeError(f"eventType is {type(eventType)}; expected str()") from None

        qry_str = """
            SELECT DISTINCT data, type, COUNT(*) AS cnt
            FROM tbl_scan_results
            WHERE scan_instance_id = :instance_id
        """

        params = {"instance_id": instanceId}

        if eventType != "ALL":
            qry_str += " AND type = :event_type"
            params["event_type"] = eventType

        if filterFp:
            qry_str += " AND false_positive <> 1"

        qry_str += " GROUP BY type, data ORDER BY cnt"

        with self.dbhLock:
            try:
                result = self.dbh.execute(text(qry_str), params)
                return result.fetchall()
            except SQLAlchemyError as e:
                raise IOError("SQL error encountered when fetching unique result events") from e

    def scanLogs(self, instanceId: str, limit: int = 0, fromRowId: int = 0, reverse: bool = False) -> list:
        """Get scan logs.

        Args:
            instanceId (str): scan instance ID
            limit (int): limit number of results
            fromRowId (int): retrieve logs starting from row ID
            reverse (bool): search result order

        Returns:
            list: scan logs

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        with self.dbhLock:
            try:
                # 기본 필터
                query = self.dbh.query(
                    ScanLog.generated,
                    ScanLog.component,
                    ScanLog.type,
                    ScanLog.message,
                    ScanLog.rowid
                ).filter(ScanLog.scan_instance_id == instanceId)

                # fromRowId 옵션 처리
                if fromRowId:
                    query = query.filter(ScanLog.rowid > fromRowId)

                # 정렬 처리
                if reverse:
                    query = query.order_by(ScanLog.generated.asc())
                else:
                    query = query.order_by(ScanLog.generated.desc())

                # LIMIT 처리
                if limit:
                    query = query.limit(limit)

                results = query.all()
                return results

            except SQLAlchemyError as e:
                raise IOError("SQL error encountered when fetching scan logs") from e

    def scanErrors(self, instanceId: str, limit: int = 0) -> list:
        """Get scan errors.

        Args:
            instanceId (str): scan instance ID
            limit (int): limit number of results

        Returns:
            list: scan errors

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(limit, int):
            raise TypeError(f"limit is {type(limit)}; expected int()") from None

        qry_str = "SELECT generated AS generated, component, message \
           FROM tbl_scan_log \
           WHERE scan_instance_id = :instance_id AND type = 'ERROR' \
           ORDER BY generated DESC"
    
        params = {"instance_id": instanceId}

        if limit is not None:
            qry_str += " LIMIT :limit"
            params["limit"] = limit

        qry = text(qry_str)

        with self.dbhLock:
            try:
                result = self.dbh.execute(qry, params)
                return result.fetchall()
            except SQLAlchemyError as e:
                raise IOError("SQL error encountered when fetching scan errors") from e

    def scanInstanceDelete(self, instanceId: str) -> bool:
        """Delete a scan instance.

        Args:
            instanceId (str): scan instance ID

        Returns:
            bool: success

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        with self.dbhLock:
            try:
                # tbl_scan_config 삭제
                self.dbh.query(ScanConfig).filter(
                    ScanConfig.scan_instance_id == instanceId
                ).delete(synchronize_session=False)

                # tbl_scan_results 삭제
                self.dbh.query(ScanResults).filter(
                    ScanResults.scan_instance_id == instanceId
                ).delete(synchronize_session=False)

                # tbl_scan_log 삭제
                self.dbh.query(ScanLog).filter(
                    ScanLog.scan_instance_id == instanceId
                ).delete(synchronize_session=False)

                # tbl_scan_instance 삭제
                self.dbh.query(ScanInstance).filter(
                    ScanInstance.guid == instanceId
                ).delete(synchronize_session=False)

                self.dbh.commit()
            except SQLAlchemyError as e:
                self.db_session.rollback()
                raise IOError("SQL error encountered when deleting scan") from e
        return True

    def scanResultsUpdateFP(self, instanceId: str, resultHashes: list, fpFlag: int) -> bool:
        """Set the false positive flag for a result.

        Args:
            instanceId (str): scan instance ID
            resultHashes (list): list of event hashes
            fpFlag (int): false positive

        Returns:
            bool: success

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(resultHashes, list):
            raise TypeError(f"resultHashes is {type(resultHashes)}; expected list") from None

        with self.dbhLock:
            try:      
                for resultHash in resultHashes:
                    stmt = (
                        update(ScanResults)
                        .where(
                            ScanResults.scan_instance_id == instanceId,
                            ScanResults.hash == resultHash
                        )
                        .values(false_positive=fpFlag)
                    )
                    self.dbh.execute(stmt)
                self.dbh.commit()
            except SQLAlchemyError as e:
                raise IOError("SQL error encountered when updating false-positive") from e
        return True

    def configSet(self, optMap: dict = {}) -> bool:
        """Store the default configuration in the database.

        Args:
            optMap (dict): config options

        Returns:
            bool: success

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
            IOError: database I/O failed
        """

        if not isinstance(optMap, dict):
            raise TypeError(f"optMap is {type(optMap)}; expected dict") from None
        if not optMap:
            raise ValueError("optMap is empty") from None

        with self.dbhLock:
            try:
                for opt, val in optMap.items():
                    if ":" in opt:
                        parts = opt.split(":")
                        scope = parts[0]
                        key = parts[1]
                    else:
                        scope = "GLOBAL"
                        key = opt

                    cfg = Config(scope=scope, opt=key, val=val)
                    self.dbh.merge(cfg) 
                self.dbh.commit()
                return True
            except SQLAlchemyError as e:
                raise IOError("SQL error encountered when storing config") from e

    def configGet(self) -> dict:
        """Retreive the config from the database

        Returns:
            dict: config

        Raises:
            IOError: database I/O failed
        """

        retval = {}

        with self.dbhLock:
            try:
                results = self.dbh.query(Config).all()
                for row in results:
                    scope = row.scope
                    opt = row.opt
                    val = row.val

                    if scope == "GLOBAL":
                        retval[opt] = val
                    else:
                        retval[f"{scope}:{opt}"] = val
                return retval
            except Exception as e:
                raise IOError("SQL error encountered when fetching configuration") from e

    def configClear(self) -> None:
        """Reset the config to default.

        Clears the config from the database and lets the hard-coded settings in the code take effect.

        Raises:
            IOError: database I/O failed
        """
        with self.dbhLock:
            try:
                self.dbh.query(Config).delete(synchronize_session=False)
                self.dbh.commit()
            except SQLAlchemyError as e:
                raise IOError("Unable to clear configuration from the database") from e

    def scanConfigSet(self, scan_id, optMap={}) -> None:
        """Store a configuration value for a scan.

        Args:
            scan_id (int): scan instance ID
            optMap (dict): config options

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
            IOError: database I/O failed
        """

        if not isinstance(optMap, dict):
            raise TypeError(f"optMap is {type(optMap)}; expected dict") from None
        if not optMap:
            raise ValueError("optMap is empty") from None
        
        with self.dbhLock:
            try:
                for opt, value in optMap.items():
                    if ":" in opt:
                        component, option = opt.split(":")
                    else:
                        component, option = "GLOBAL", opt

                    cfg = ScanConfig(
                        scan_instance_id=scan_id,
                        component=component,
                        opt=option,
                        val=value
                    )
                    self.dbh.merge(cfg)
                self.dbh.commit()
            except SQLAlchemyError as e:
                self.dbh.rollback()
                raise IOError("SQL error encountered when storing config, aborting") from e

    def scanConfigGet(self, instanceId: str) -> dict:
        """Retrieve configuration data for a scan component.

        Args:
            instanceId (str): scan instance ID

        Returns:
            dict: configuration data

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        retval = {}

        with self.dbhLock:
            try:
                rows = (
                    self.dbh.query(ScanConfig)
                    .filter(ScanConfig.scan_instance_id == instanceId)
                    .order_by(ScanConfig.component, ScanConfig.opt)
                    .all()
                )
                for row in rows:
                    if row.component == "GLOBAL":
                        retval[row.opt] = row.val
                    else:
                        retval[f"{row.component}:{row.opt}"] = row.val
                return retval
            except SQLAlchemyError as e:
                raise IOError("SQL error encountered when fetching configuration") from e

    def scanEventStore(self, instanceId: str, sfEvent, truncateSize: int = 0) -> None:
        """Store an event in the database.

        Args:
            instanceId (str): scan instance ID
            sfEvent (SpiderFootEvent): event to be stored in the database
            truncateSize (int): truncate size for event data

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
            IOError: database I/O failed
        """
        from spiderfoot import SpiderFootEvent

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not instanceId:
            raise ValueError("instanceId is empty") from None

        if not isinstance(sfEvent, SpiderFootEvent):
            raise TypeError(f"sfEvent is {type(sfEvent)}; expected SpiderFootEvent()") from None

        if not isinstance(sfEvent.generated, float):
            raise TypeError(f"sfEvent.generated is {type(sfEvent.generated)}; expected float()") from None

        if not sfEvent.generated:
            raise ValueError("sfEvent.generated is empty") from None

        if not isinstance(sfEvent.eventType, str):
            raise TypeError(f"sfEvent.eventType is {type(sfEvent.eventType,)}; expected str()") from None

        if not sfEvent.eventType:
            raise ValueError("sfEvent.eventType is empty") from None

        if not isinstance(sfEvent.data, str):
            raise TypeError(f"sfEvent.data is {type(sfEvent.data)}; expected str()") from None

        if not sfEvent.data:
            raise ValueError("sfEvent.data is empty") from None

        if not isinstance(sfEvent.module, str):
            raise TypeError(f"sfEvent.module is {type(sfEvent.module)}; expected str()") from None

        if not sfEvent.module and sfEvent.eventType != "ROOT":
            raise ValueError("sfEvent.module is empty") from None

        if not isinstance(sfEvent.confidence, int):
            raise TypeError(f"sfEvent.confidence is {type(sfEvent.confidence)}; expected int()") from None

        if not 0 <= sfEvent.confidence <= 100:
            raise ValueError(f"sfEvent.confidence value is {type(sfEvent.confidence)}; expected 0 - 100") from None

        if not isinstance(sfEvent.visibility, int):
            raise TypeError(f"sfEvent.visibility is {type(sfEvent.visibility)}; expected int()") from None

        if not 0 <= sfEvent.visibility <= 100:
            raise ValueError(f"sfEvent.visibility value is {type(sfEvent.visibility)}; expected 0 - 100") from None

        if not isinstance(sfEvent.risk, int):
            raise TypeError(f"sfEvent.risk is {type(sfEvent.risk)}; expected int()") from None

        if not 0 <= sfEvent.risk <= 100:
            raise ValueError(f"sfEvent.risk value is {type(sfEvent.risk)}; expected 0 - 100") from None

        if not isinstance(sfEvent.sourceEvent, SpiderFootEvent) and sfEvent.eventType != "ROOT":
            raise TypeError(f"sfEvent.sourceEvent is {type(sfEvent.sourceEvent)}; expected str()") from None

        if not isinstance(sfEvent.sourceEventHash, str):
            raise TypeError(f"sfEvent.sourceEventHash is {type(sfEvent.sourceEventHash)}; expected str()") from None

        if not sfEvent.sourceEventHash:
            raise ValueError("sfEvent.sourceEventHash is empty") from None

        storeData = sfEvent.data

        # truncate if required
        if isinstance(truncateSize, int) and truncateSize > 0:
            storeData = storeData[0:truncateSize]

        # ORM 객체 생성
        new_result = ScanResults(
            scan_instance_id=instanceId,
            hash=sfEvent.hash,
            type=sfEvent.eventType,
            generated=sfEvent.generated,
            confidence=sfEvent.confidence,
            visibility=sfEvent.visibility,
            risk=sfEvent.risk,
            module=sfEvent.module,
            data=storeData,
            source_event_hash=sfEvent.sourceEventHash
        )

        with self.dbhLock:
            try:
                self.dbh.add(new_result)
                self.dbh.commit()
            except SQLAlchemyError as e:
                self.db_session.rollback()
                raise IOError("SQL error encountered when storing event data") from e

    def scanInstanceList(self) -> list:
        """List all previously run scans.

        Returns:
            list: previously run scans

        Raises:
            IOError: database I/O failed
        """

        # SQLite doesn't support OUTER JOINs, so we need a work-around that
        # does a UNION of scans with results and scans without results to
        # get a complete listing.
        qry = text("""
            SELECT i.guid, i.name, i.seed_target, ROUND(i.created/1000),
                ROUND(i.started)/1000 as started, ROUND(i.ended)/1000,
                i.status, COUNT(r.type)
            FROM tbl_scan_instance i
            JOIN tbl_scan_results r ON i.guid = r.scan_instance_id
            WHERE r.type <> 'ROOT'
            GROUP BY i.guid

            UNION ALL

            SELECT i.guid, i.name, i.seed_target, ROUND(i.created/1000),
                ROUND(i.started)/1000 as started, ROUND(i.ended)/1000,
                i.status, '0'
            FROM tbl_scan_instance i
            WHERE i.guid NOT IN (
                SELECT DISTINCT scan_instance_id
                FROM tbl_scan_results
                WHERE type <> 'ROOT'
            )
            ORDER BY started DESC
        """)

        with self.dbhLock:
            try:
                result = self.dbh.execute(qry)
                return result.fetchall()
            except Exception as e:
                raise IOError("SQL error encountered when fetching scan list") from e

    def scanResultHistory(self, instanceId: str) -> list:
        """History of data from the scan.

        Args:
            instanceId (str): scan instance ID

        Returns:
            list: scan data history

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        qry = text("""
            SELECT STRFTIME('%H:%M %w', generated / 1000, 'unixepoch') AS hourmin,
                type,
                COUNT(*) AS cnt
            FROM tbl_scan_results
            WHERE scan_instance_id = :instance_id
            GROUP BY hourmin, type
        """)

        qvars = [instanceId]

        with self.dbhLock:
            try:
                result = self.dbh.execute(qry, {"instance_id": instanceId})
                return result.fetchall()
            except SQLAlchemyError as e:
                raise IOError(f"SQL error encountered when fetching history for scan {instanceId}") from e

    def scanElementSourcesDirect(self, instanceId: str, elementIdList: list) -> list:
        """Get the source IDs, types and data for a set of IDs.

        Args:
            instanceId (str): scan instance ID
            elementIdList (list): TBD

        Returns:
            list: TBD

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()") from None

        if not isinstance(elementIdList, list):
            raise TypeError(f"elementIdList is {type(elementIdList)}; expected list") from None

        hashIds = []
        for hashId in elementIdList:
            if not hashId:
                continue
            if not hashId.isalnum():
                continue
            hashIds.append(hashId)
        
        if not hashIds:
            return []

        placeholders = ", ".join([f":hash{i}" for i in range(len(hashIds))])
        qry = text(f"""
            SELECT 
                ROUND(c.generated) AS generated,
                c.data,
                s.data AS source_data,
                c.module,
                c.type,
                c.confidence,
                c.visibility,
                c.risk,
                c.hash,
                c.source_event_hash,
                t.event_descr,
                t.event_type,
                s.scan_instance_id,
                c.false_positive AS fp,
                s.false_positive AS parent_fp,
                s.type,
                s.module,
                st.event_type AS source_entity_type
            FROM tbl_scan_results c
            JOIN tbl_scan_results s
                ON c.source_event_hash = s.hash
            AND s.scan_instance_id = c.scan_instance_id
            JOIN tbl_event_types t
                ON t.event = c.type
            JOIN tbl_event_types st
                ON st.event = s.type
            WHERE c.scan_instance_id = :instance_id
            AND c.hash IN ({placeholders})
        """)

        params = {"instance_id": instanceId}
        for i, h in enumerate(hashIds):
            params[f"hash{i}"] = h

        with self.dbhLock:
            try:
                result = self.dbh.execute(qry, params)
                return result.fetchall()
            except SQLAlchemyError as e:
                raise IOError("SQL error encountered when getting source element IDs") from e

    def scanElementChildrenDirect(self, instanceId: str, elementIdList: list) -> list:
        """Get the child IDs, types and data for a set of IDs.

        Args:
            instanceId (str): scan instance ID
            elementIdList (list): TBD

        Returns:
            list: TBD

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()")

        if not isinstance(elementIdList, list):
            raise TypeError(f"elementIdList is {type(elementIdList)}; expected list")

        hashIds = []
        for hashId in elementIdList:
            if not hashId:
                continue
            if not hashId.isalnum():
                continue
            hashIds.append(hashId)

         # IN 절용 파라미터 생성
        placeholders = ", ".join([f":hash{i}" for i in range(len(hashIds))])

        qry = text(f"""
            SELECT 
                ROUND(c.generated) AS generated,
                c.data,
                s.data AS source_data,
                c.module,
                c.type,
                c.confidence,
                c.visibility,
                c.risk,
                c.hash,
                c.source_event_hash,
                t.event_descr,
                t.event_type,
                s.scan_instance_id,
                c.false_positive AS fp,
                s.false_positive AS parent_fp
            FROM tbl_scan_results c
            JOIN tbl_scan_results s
                ON c.source_event_hash = s.hash
            AND s.scan_instance_id = c.scan_instance_id
            JOIN tbl_event_types t
                ON t.event = c.type
            WHERE c.scan_instance_id = :instance_id
            AND s.hash IN ({placeholders})
        """)

        # 파라미터 딕셔너리 생성
        params = {"instance_id": instanceId}
        for i, h in enumerate(hashIds):
            params[f"hash{i}"] = h

        with self.dbhLock:
            try:
                result = self.dbh.execute(qry, params)
                return result.fetchall()
            except SQLAlchemyError as e:
                raise IOError("SQL error encountered when getting child element IDs") from e

    def scanElementSourcesAll(self, instanceId: str, childData: list) -> list:
        """Get the full set of upstream IDs which are parents to the supplied set of IDs.

        Args:
            instanceId (str): scan instance ID
            childData (list): TBD

        Returns:
            list: TBD

        Raises:
            TypeError: arg type was invalid
            ValueError: arg value was invalid
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()")

        if not isinstance(childData, list):
            raise TypeError(f"childData is {type(childData)}; expected list")

        if not childData:
            raise ValueError("childData is empty")

        # Get the first round of source IDs for the leafs
        keepGoing = True
        nextIds = []
        datamap = {}
        pc = {}

        for row in childData:
            # these must be unique values!
            parentId = row[9]
            childId = row[8]
            datamap[childId] = tuple(row)

            if parentId in pc:
                if childId not in pc[parentId]:
                    pc[parentId].append(childId)
            else:
                pc[parentId] = [childId]

            # parents of the leaf set
            if parentId not in nextIds:
                nextIds.append(parentId)

        while keepGoing:
            parentSet = self.scanElementSourcesDirect(instanceId, nextIds)
            nextIds = []
            keepGoing = False

            for row in parentSet:
                parentId = row[9]
                childId = row[8]
                datamap[childId] = tuple(row)

                if parentId in pc:
                    if childId not in pc[parentId]:
                        pc[parentId].append(childId)
                else:
                    pc[parentId] = [childId]
                if parentId not in nextIds:
                    nextIds.append(parentId)

                # Prevent us from looping at root
                if parentId != "ROOT":
                    keepGoing = True

        datamap[parentId] = tuple(row)
        return [datamap, pc]

    def scanElementChildrenAll(self, instanceId: str, parentIds: list) -> list:
        """Get the full set of downstream IDs which are children of the supplied set of IDs.

        Args:
            instanceId (str): scan instance ID
            parentIds (list): TBD

        Returns:
            list: TBD

        Raises:
            TypeError: arg type was invalid

        Note: This function is not the same as the scanElementParent* functions.
              This function returns only ids.
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()")

        if not isinstance(parentIds, list):
            raise TypeError(f"parentIds is {type(parentIds)}; expected list")

        datamap = []
        keepGoing = True
        nextIds = []

        nextSet = self.scanElementChildrenDirect(instanceId, parentIds)
        for row in nextSet:
            datamap.append(row[8])

        for row in nextSet:
            if row[8] not in nextIds:
                nextIds.append(row[8])

        while keepGoing:
            nextSet = self.scanElementChildrenDirect(instanceId, nextIds)
            if nextSet is None or len(nextSet) == 0:
                keepGoing = False
                break

            for row in nextSet:
                datamap.append(row[8])
                nextIds = []
                nextIds.append(row[8])

        return datamap

    def correlationResultCreate(
        self,
        instanceId: str,
        ruleId: str,
        ruleName: str,
        ruleDescr: str,
        ruleRisk: str,
        ruleYaml: str,
        correlationTitle: str,
        eventHashes: list
    ) -> str:
        """Create a correlation result in the database.

        Args:
            instanceId (str): scan instance ID
            ruleId(str): correlation rule ID
            ruleName(str): correlation rule name
            ruleDescr(str): correlation rule description
            ruleRisk(str): correlation rule risk level
            ruleYaml(str): correlation rule raw YAML
            correlationTitle(str): correlation title
            eventHashes(list): events mapped to the correlation result

        Raises:
            TypeError: arg type was invalid
            IOError: database I/O failed

        Returns:
            str: Correlation ID created
        """

        if not isinstance(instanceId, str):
            raise TypeError(f"instanceId is {type(instanceId)}; expected str()")

        if not isinstance(ruleId, str):
            raise TypeError(f"ruleId is {type(ruleId)}; expected str()")

        if not isinstance(ruleName, str):
            raise TypeError(f"ruleName is {type(ruleName)}; expected str()")

        if not isinstance(ruleDescr, str):
            raise TypeError(f"ruleDescr is {type(ruleDescr)}; expected str()")

        if not isinstance(ruleRisk, str):
            raise TypeError(f"ruleRisk is {type(ruleRisk)}; expected str()")

        if not isinstance(ruleYaml, str):
            raise TypeError(f"ruleYaml is {type(ruleYaml)}; expected str()")

        if not isinstance(correlationTitle, str):
            raise TypeError(f"correlationTitle is {type(correlationTitle)}; expected str()")

        if not isinstance(eventHashes, list):
            raise TypeError(f"eventHashes is {type(eventHashes)}; expected list")

        uniqueId = str(hashlib.md5(str(time.time() + random.SystemRandom().randint(0, 99999999)).encode('utf-8')).hexdigest())  # noqa: DUO130

        new_result = ScanCorrelationResults(
            id=uniqueId,
            scan_instance_id=instanceId,
            title=correlationTitle,
            rule_name=ruleName,
            rule_descr=ruleDescr,
            rule_risk=ruleRisk,
            rule_id=ruleId,
            rule_logic=ruleYaml
        )

        with self.dbhLock:
            try:
                self.dbh.add(new_result)
                self.dbh.commit()
            except SQLAlchemyError as e:
                raise IOError("Unable to create correlation result in database") from e

        # Map events to the correlation result
        with self.dbhLock:
            for eventHash in eventHashes:
                try:
                    new_result_event = ScanCorrelationResultsEvents(
                        correlation_id=uniqueId,
                        event_hash=eventHash
                    )
                    self.dbh.add(new_result_event)
                    self.dbh.commit()
                except SQLAlchemyError as e:
                    raise IOError("Unable to create correlation result in database") from e

        return uniqueId
