#
# Copyright (c) 2023 Airbyte, Inc., all rights reserved.
#

import json
from unittest.mock import patch

import mock
import pendulum
import pytest
from source_hubspot.streams import (
    Companies,
    ContactLists,
    Contacts,
    ContactsListMemberships,
    ContactsMergedAudit,
    ContactsWebAnalytics,
    CustomObject,
    Deals,
    DealsArchived,
    DealSplits,
    EngagementsCalls,
    EngagementsEmails,
    EngagementsMeetings,
    EngagementsNotes,
    EngagementsTasks,
    Forms,
    FormSubmissions,
    Goals,
    Leads,
    LineItems,
    Owners,
    OwnersArchived,
    Products,
    RecordUnnester,
    Tickets,
)

from airbyte_cdk.models import SyncMode

from .conftest import find_stream
from .utils import read_full_refresh, read_incremental


@pytest.fixture(autouse=True)
def time_sleep_mock(mocker):
    time_mock = mocker.patch("time.sleep", lambda x: None)
    yield time_mock


def test_updated_at_field_non_exist_handler(requests_mock, common_params, fake_properties_list):
    stream = ContactLists(**common_params)

    responses = [
        {
            "json": {
                stream.data_field: [
                    {
                        "id": "test_id",
                        "createdAt": "2022-03-25T16:43:11Z",
                    },
                ],
            }
        }
    ]
    properties_response = [
        {
            "json": [
                {"name": property_name, "type": "string", "updatedAt": 1571085954360, "createdAt": 1565059306048}
                for property_name in fake_properties_list
            ],
            "status_code": 200,
        }
    ]

    requests_mock.register_uri("GET", stream.url, responses)
    requests_mock.register_uri("GET", "/properties/v2/contact/properties", properties_response)

    _, stream_state = read_incremental(stream, {})

    expected = int(pendulum.parse(common_params["start_date"]).timestamp() * 1000)

    assert stream_state[stream.updated_at_field] == expected


@pytest.mark.parametrize(
    "stream_class, endpoint, cursor_value",
    [
        ("campaigns", "campaigns", {"lastUpdatedTime": 1675121674226}),
        (Companies, "company", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (ContactLists, "contact", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (Contacts, "contact", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (ContactsMergedAudit, "contact", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (Deals, "deal", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (DealsArchived, "deal", {"archivedAt": "2022-02-25T16:43:11Z"}),
        ("deal_pipelines", "deal", {"updatedAt": 1675121674226}),
        (DealSplits, "deal_split", {"updatedAt": "2022-02-25T16:43:11Z"}),
        ("email_events", "", {"updatedAt": "2022-02-25T16:43:11Z"}),
        ("email_subscriptions", "", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (EngagementsCalls, "calls", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (EngagementsEmails, "emails", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (EngagementsMeetings, "meetings", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (EngagementsNotes, "notes", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (EngagementsTasks, "tasks", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (Forms, "form", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (FormSubmissions, "form", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (Goals, "goal_targets", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (Leads, "leads", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (LineItems, "line_item", {"updatedAt": "2022-02-25T16:43:11Z"}),
        ("marketing_emails", "", {"updated": "1634050455543"}),
        (Owners, "", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (OwnersArchived, "", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (Products, "product", {"updatedAt": "2022-02-25T16:43:11Z"}),
        ("ticket_pipelines", "", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (Tickets, "ticket", {"updatedAt": "2022-02-25T16:43:11Z"}),
        ("workflows", "", {"updatedAt": 1675121674226}),
    ],
)
@mock.patch("source_hubspot.source.SourceHubspot.get_custom_object_streams")
def test_streams_read(
    mock_get_custom_object_streams, stream_class, endpoint, cursor_value, requests_mock, common_params, fake_properties_list, config
):
    if isinstance(stream_class, str):
        stream = find_stream(stream_class, config)
        data_field = (
            stream.retriever.record_selector.extractor.field_path[0]
            if len(stream.retriever.record_selector.extractor.field_path) > 0
            else None
        )
    else:
        stream = stream_class(**common_params)
        data_field = stream.data_field
    list_entities = [
        {
            "id": "test_id",
            "created": "2022-02-25T16:43:11Z",
        }
        | cursor_value
    ]
    responses = [{"json": {data_field: list_entities} if data_field else list_entities}]

    properties_response = [
        {
            "json": [
                {"name": property_name, "type": "string", "updatedAt": 1571085954360, "createdAt": 1565059306048}
                for property_name in fake_properties_list
            ],
            "status_code": 200,
        }
    ]

    contact_response = [
        {
            "json": {
                data_field: [
                    {"id": "test_id", "created": "2022-06-25T16:43:11Z", "properties": {"hs_merged_object_ids": "test_id"}} | cursor_value
                ],
            }
        }
    ]

    read_batch_contact_v1_response = [
        {
            "json": {
                "test_id": {"vid": "test_id", "merge-audits": [{"canonical-vid": 2, "vid-to-merge": 5608, "timestamp": 1653322839932}]}
            },
            "status_code": 200,
        }
    ]

    contact_lists_v1_response = [
        {
            "json": {
                "contacts": [{"vid": "test_id", "merge-audits": [{"canonical-vid": 2, "vid-to-merge": 5608, "timestamp": 1653322839932}]}]
            },
            "status_code": 200,
        }
    ]

    is_form_submission = isinstance(stream, FormSubmissions)
    stream._sync_mode = SyncMode.full_refresh
    if isinstance(stream_class, str):
        stream_url = stream.retriever.requester.url_base + stream.retriever.requester.path
    else:
        stream_url = stream.url + "/test_id" if is_form_submission else stream.url
    stream._sync_mode = None

    requests_mock.register_uri("GET", stream_url, responses)
    requests_mock.register_uri("GET", "/crm/v3/objects/contact", contact_response)
    requests_mock.register_uri("GET", "/contacts/v1/lists/all/contacts/all", contact_lists_v1_response)
    requests_mock.register_uri("GET", "/marketing/v3/forms", responses)
    requests_mock.register_uri("GET", "/email/public/v1/campaigns/test_id", responses)
    requests_mock.register_uri("GET", "/email/public/v1/campaigns?count=500", [{"json": {"campaigns": list_entities}}])
    requests_mock.register_uri("GET", f"/properties/v2/{endpoint}/properties", properties_response)
    requests_mock.register_uri("GET", "/contacts/v1/contact/vids/batch/", read_batch_contact_v1_response)

    records = read_full_refresh(stream)
    assert records


@pytest.mark.parametrize(
    "stream, endpoint, cursor_value",
    [
        (Contacts, "contact", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (Deals, "deal", {"updatedAt": "2022-02-25T16:43:11Z"}),
        (DealsArchived, "deal", {"archivedAt": "2022-02-25T16:43:11Z"}),
    ],
    ids=[
        "Contacts stream with v2 field transformations",
        "Deals stream with v2 field transformations",
        "DealsArchived stream with v2 field transformations",
    ],
)
def test_stream_read_with_legacy_field_transformation(
    stream, endpoint, cursor_value, requests_mock, common_params, fake_properties_list, migrated_properties_list
):
    stream = stream(**common_params)
    responses = [
        {
            "json": {
                stream.data_field: [
                    {
                        "id": "test_id",
                        "created": "2022-02-25T16:43:11Z",
                        "properties": {
                            "hs_v2_latest_time_in_prospect": "1 month",
                            "hs_v2_date_entered_prospect": "2024-01-01T00:00:00Z",
                            "hs_v2_date_exited_prospect": "2024-02-01T00:00:00Z",
                            "hs_v2_cumulative_time_in_prsopect": "1 month",
                            "hs_v2_some_other_property_in_prospect": "Great property",
                        },
                    }
                    | cursor_value
                ],
            }
        }
    ]
    fake_properties_list.extend(migrated_properties_list)
    properties_response = [
        {
            "json": [
                {"name": property_name, "type": "string", "updatedAt": 1571085954360, "createdAt": 1565059306048}
                for property_name in fake_properties_list
            ],
            "status_code": 200,
        }
    ]
    stream._sync_mode = SyncMode.full_refresh

    requests_mock.register_uri("GET", stream.url, responses)
    requests_mock.register_uri("GET", f"/properties/v2/{endpoint}/properties", properties_response)

    records = read_full_refresh(stream)
    assert records
    expected_record = {
        "id": "test_id",
        "created": "2022-02-25T16:43:11Z",
        "properties": {
            "hs_v2_date_entered_prospect": "2024-01-01T00:00:00Z",
            "hs_v2_date_exited_prospect": "2024-02-01T00:00:00Z",
            "hs_v2_latest_time_in_prospect": "1 month",
            "hs_v2_cumulative_time_in_prsopect": "1 month",
            "hs_v2_some_other_property_in_prospect": "Great property",
            "hs_time_in_prospect": "1 month",
            "hs_date_exited_prospect": "2024-02-01T00:00:00Z",
        },
        "properties_hs_v2_date_entered_prospect": "2024-01-01T00:00:00Z",
        "properties_hs_v2_date_exited_prospect": "2024-02-01T00:00:00Z",
        "properties_hs_v2_latest_time_in_prospect": "1 month",
        "properties_hs_v2_cumulative_time_in_prsopect": "1 month",
        "properties_hs_v2_some_other_property_in_prospect": "Great property",
        "properties_hs_time_in_prospect": "1 month",
        "properties_hs_date_exited_prospect": "2024-02-01T00:00:00Z",
    } | cursor_value
    if isinstance(stream, Contacts):
        expected_record = expected_record | {"properties_hs_lifecyclestage_prospect_date": "2024-01-01T00:00:00Z"}
        expected_record["properties"] = expected_record["properties"] | {"hs_lifecyclestage_prospect_date": "2024-01-01T00:00:00Z"}
    else:
        expected_record = expected_record | {"properties_hs_date_entered_prospect": "2024-01-01T00:00:00Z"}
        expected_record["properties"] = expected_record["properties"] | {"hs_date_entered_prospect": "2024-01-01T00:00:00Z"}
    assert records[0] == expected_record


@pytest.mark.parametrize("sync_mode", [SyncMode.full_refresh, SyncMode.incremental])
def test_crm_search_streams_with_no_associations(sync_mode, common_params, requests_mock, fake_properties_list):
    stream = DealSplits(**common_params)
    stream_state = {
        "type": "STREAM",
        "stream": {"stream_descriptor": {"name": "deal_splits"}, "stream_state": {"updatedAt": "2021-01-01T00:00:00.000000Z"}},
    }
    cursor_value = {"updatedAt": "2022-02-25T16:43:11Z"}
    responses = [
        {
            "json": {
                stream.data_field: [
                    {
                        "id": "test_id",
                        "created": "2022-02-25T16:43:11Z",
                    }
                    | cursor_value
                ],
            }
        }
    ]
    if sync_mode == SyncMode.full_refresh:
        stream.set_sync(SyncMode.full_refresh, stream_state=None)
        endpoint_path = f"/crm/v3/objects/{stream.entity}"
        requests_mock.register_uri("GET", endpoint_path, responses)
    else:
        stream.set_sync(SyncMode.incremental, stream_state)
        endpoint_path = f"/crm/v3/objects/{stream.entity}/search"
        requests_mock.register_uri("POST", endpoint_path, responses)
    properties_path = f"/properties/v2/{stream.entity}/properties"
    properties_response = [
        {
            "json": [
                {"name": property_name, "type": "string", "updatedAt": 1571085954360, "createdAt": 1565059306048}
                for property_name in fake_properties_list
            ],
            "status_code": 200,
        }
    ]
    stream._sync_mode = sync_mode
    requests_mock.register_uri("POST", endpoint_path, responses)
    requests_mock.register_uri("GET", properties_path, properties_response)
    if sync_mode == SyncMode.incremental:
        records, state = read_incremental(stream, stream_state=stream_state)
        assert state
    else:
        records = read_full_refresh(stream)
    assert records


@pytest.mark.parametrize(
    "error_response",
    [
        {"json": {}, "status_code": 429},
        {"json": {}, "status_code": 502},
        {"json": {}, "status_code": 504},
        {"text": "Not a JSON", "status_code": 200},
    ],
)
def test_common_error_retry(error_response, requests_mock, common_params, fake_properties_list):
    """Error once, check that we retry and not fail"""
    properties_response = [
        {"name": property_name, "type": "string", "updatedAt": 1571085954360, "createdAt": 1565059306048}
        for property_name in fake_properties_list
    ]
    responses = [
        error_response,
        {
            "json": properties_response,
            "status_code": 200,
        },
    ]

    stream = Companies(**common_params)

    response = {
        stream.data_field: [
            {
                "id": "test_id",
                "created": "2022-02-25T16:43:11Z",
                "updatedAt": "2022-02-25T16:43:11Z",
                "lastUpdatedTime": "2022-02-25T16:43:11Z",
            }
        ],
    }
    requests_mock.register_uri("GET", "/properties/v2/company/properties", responses)
    stream._sync_mode = SyncMode.full_refresh
    stream_url = stream.url
    stream._sync_mode = None
    requests_mock.register_uri("GET", stream_url, [{"json": response}])
    records = read_full_refresh(stream)

    assert [response[stream.data_field][0]] == records
    assert len(requests_mock.request_history) > 1


def test_contact_lists_transform(requests_mock, common_params):
    stream = ContactLists(**common_params)

    responses = [
        {
            "json": {
                stream.data_field: [
                    {
                        "listId": 1,
                        "createdAt": 1654117200000,
                        "filters": [[{"value": "@hubspot"}]],
                    },
                    {
                        "listId": 2,
                        "createdAt": 1654117200001,
                        "filters": [[{"value": True}, {"value": "FORM_ABUSE"}]],
                    },
                    {
                        "listId": 3,
                        "createdAt": 1654117200002,
                        "filters": [[{"value": 1000}]],
                    },
                ]
            }
        }
    ]

    requests_mock.register_uri("GET", stream.url, responses)
    records = read_full_refresh(stream)

    assert records[0]["filters"][0][0]["value"] == "@hubspot"
    assert records[1]["filters"][0][0]["value"] == "True"
    assert records[1]["filters"][0][1]["value"] == "FORM_ABUSE"
    assert records[2]["filters"][0][0]["value"] == "1000"


def test_client_side_incremental_stream(requests_mock, common_params, fake_properties_list):
    stream = Forms(**common_params)
    latest_cursor_value = "2030-01-30T23:46:36.287Z"
    responses = [
        {
            "json": {
                stream.data_field: [
                    {"id": "test_id_1", "createdAt": "2022-03-25T16:43:11Z", "updatedAt": "2023-01-30T23:46:36.287Z"},
                    {"id": "test_id_2", "createdAt": "2022-03-25T16:43:11Z", "updatedAt": latest_cursor_value},
                    {"id": "test_id_3", "createdAt": "2022-03-25T16:43:11Z", "updatedAt": "2023-02-20T23:46:36.287Z"},
                ],
            }
        }
    ]
    properties_response = [
        {
            "json": [
                {"name": property_name, "type": "string", "createdAt": "2023-01-30T23:46:24.355Z", "updatedAt": "2023-01-30T23:46:36.287Z"}
                for property_name in fake_properties_list
            ],
            "status_code": 200,
        }
    ]

    requests_mock.register_uri("GET", stream.url, responses)
    requests_mock.register_uri("GET", "/properties/v2/form/properties", properties_response)

    list(stream.read_records(SyncMode.incremental))
    assert stream.state == {stream.cursor_field: pendulum.parse(latest_cursor_value).to_rfc3339_string()}


@pytest.mark.parametrize(
    "state, record, expected",
    [
        (
            {"updatedAt": ""},
            {"id": "test_id_1", "updatedAt": "2023-01-30T23:46:36.287Z"},
            (True, {"updatedAt": "2023-01-30T23:46:36.287000+00:00"}),
        ),
        (
            {"updatedAt": "2023-01-30T23:46:36.287000+00:00"},
            {"id": "test_id_1", "updatedAt": "2023-01-29T01:02:03.123Z"},
            (False, {"updatedAt": "2023-01-30T23:46:36.287000+00:00"}),
        ),
    ],
    ids=[
        "Empty Sting in state + new record",
        "State + old record",
    ],
)
def test_empty_string_in_state(state, record, expected, requests_mock, common_params, fake_properties_list):
    stream = Forms(**common_params)
    stream.state = state
    # overcome the availability strartegy issues by mocking the responses
    # A.K.A: not related to the test at all, but definetely required.
    properties_response = [
        {
            "json": [
                {"name": property_name, "type": "string", "CreatedAt": "2023-01-30T23:46:24.355Z", "updatedAt": "2023-01-30T23:46:36.287Z"}
                for property_name in fake_properties_list
            ],
            "status_code": 200,
        }
    ]
    requests_mock.register_uri("GET", stream.url, json=record)
    requests_mock.register_uri("GET", "/properties/v2/form/properties", properties_response)
    # end of mocking `availability strategy`

    result = stream.filter_by_state(stream.state, record)
    assert result == expected[0]
    assert stream.state == expected[1]


@pytest.fixture(name="custom_object_schema")
def custom_object_schema_fixture():
    return {
        "labels": {"this": "that"},
        "requiredProperties": ["name"],
        "searchableProperties": ["name"],
        "primaryDisplayProperty": "name",
        "secondaryDisplayProperties": [],
        "archived": False,
        "restorable": True,
        "metaType": "PORTAL_SPECIFIC",
        "id": "7232155",
        "fullyQualifiedName": "p19936848_Animal",
        "createdAt": "2022-06-17T18:40:27.019Z",
        "updatedAt": "2022-06-17T18:40:27.019Z",
        "objectTypeId": "2-7232155",
        "properties": [
            {
                "name": "name",
                "label": "Animal name",
                "type": "string",
                "fieldType": "text",
                "description": "The animal name.",
                "groupName": "animal_information",
                "options": [],
                "displayOrder": -1,
                "calculated": False,
                "externalOptions": False,
                "hasUniqueValue": False,
                "hidden": False,
                "hubspotDefined": False,
                "modificationMetadata": {"archivable": True, "readOnlyDefinition": True, "readOnlyValue": False},
                "formField": True,
            }
        ],
        "associations": [],
        "name": "animals",
    }


@pytest.fixture(name="expected_custom_object_json_schema")
def expected_custom_object_json_schema():
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": ["null", "object"],
        "additionalProperties": True,
        "properties": {
            "id": {"type": ["null", "string"]},
            "createdAt": {"type": ["null", "string"], "format": "date-time"},
            "updatedAt": {"type": ["null", "string"], "format": "date-time"},
            "archived": {"type": ["null", "boolean"]},
            "properties": {"type": ["null", "object"], "properties": {"name": {"type": ["null", "string"]}}},
            "properties_name": {"type": ["null", "string"]},
        },
    }


def test_custom_object_stream_doesnt_call_hubspot_to_get_json_schema_if_available(
    requests_mock, custom_object_schema, expected_custom_object_json_schema, common_params
):
    stream = CustomObject(
        entity="animals",
        schema=expected_custom_object_json_schema,
        fully_qualified_name="p123_animals",
        custom_properties={"name": {"type": ["null", "string"]}},
        **common_params,
    )

    adapter = requests_mock.register_uri("GET", "/crm/v3/schemas", [{"json": {"results": [custom_object_schema]}}])
    json_schema = stream.get_json_schema()

    assert json_schema == expected_custom_object_json_schema
    assert not adapter.called


def test_contacts_merged_audit_stream_doesnt_call_hubspot_to_get_json_schema(requests_mock, common_params):
    stream = ContactsMergedAudit(**common_params)

    adapter = requests_mock.register_uri(
        "GET",
        f"/properties/v2/{stream.entity}/properties",
        [
            {
                "json": [
                    {
                        "name": "hs_object_id",
                        "label": "Record ID",
                        "type": "number",
                    }
                ]
            }
        ],
    )
    _ = stream.get_json_schema()

    assert not adapter.called


def test_get_custom_objects_metadata_success(requests_mock, custom_object_schema, expected_custom_object_json_schema, api):
    requests_mock.register_uri("GET", "/crm/v3/schemas", json={"results": [custom_object_schema]})
    for entity, fully_qualified_name, schema, custom_properties in api.get_custom_objects_metadata():
        assert entity == "animals"
        assert fully_qualified_name == "p19936848_Animal"
        assert schema == expected_custom_object_json_schema


@pytest.mark.parametrize(
    "input_data, unnest_fields, expected_output",
    (
        (
            [{"id": 1, "createdAt": "2020-01-01", "email": {"from": "integration-test@airbyte.io", "to": "michael_scott@gmail.com"}}],
            [],
            [{"id": 1, "createdAt": "2020-01-01", "email": {"from": "integration-test@airbyte.io", "to": "michael_scott@gmail.com"}}],
        ),
        (
            [
                {
                    "id": 1,
                    "createdAt": "2020-01-01",
                    "email": {"from": "integration-test@airbyte.io", "to": "michael_scott@gmail.com"},
                    "properties": {"phone": "+38044-111-111", "address": "31, Cleveland str, Washington DC"},
                }
            ],
            [],
            [
                {
                    "id": 1,
                    "createdAt": "2020-01-01",
                    "email": {"from": "integration-test@airbyte.io", "to": "michael_scott@gmail.com"},
                    "properties": {"phone": "+38044-111-111", "address": "31, Cleveland str, Washington DC"},
                    "properties_phone": "+38044-111-111",
                    "properties_address": "31, Cleveland str, Washington DC",
                }
            ],
        ),
        (
            [
                {
                    "id": 1,
                    "createdAt": "2020-01-01",
                    "email": {"from": "integration-test@airbyte.io", "to": "michael_scott@gmail.com"},
                }
            ],
            ["email"],
            [
                {
                    "id": 1,
                    "createdAt": "2020-01-01",
                    "email": {"from": "integration-test@airbyte.io", "to": "michael_scott@gmail.com"},
                    "email_from": "integration-test@airbyte.io",
                    "email_to": "michael_scott@gmail.com",
                }
            ],
        ),
        (
            [
                {
                    "id": 1,
                    "createdAt": "2020-01-01",
                    "email": {"from": "integration-test@airbyte.io", "to": "michael_scott@gmail.com"},
                    "properties": {"phone": "+38044-111-111", "address": "31, Cleveland str, Washington DC"},
                }
            ],
            ["email"],
            [
                {
                    "id": 1,
                    "createdAt": "2020-01-01",
                    "email": {"from": "integration-test@airbyte.io", "to": "michael_scott@gmail.com"},
                    "email_from": "integration-test@airbyte.io",
                    "email_to": "michael_scott@gmail.com",
                    "properties": {"phone": "+38044-111-111", "address": "31, Cleveland str, Washington DC"},
                    "properties_phone": "+38044-111-111",
                    "properties_address": "31, Cleveland str, Washington DC",
                }
            ],
        ),
    ),
)
def test_records_unnester(input_data, unnest_fields, expected_output):
    unnester = RecordUnnester(fields=unnest_fields)
    assert list(unnester.unnest(input_data)) == expected_output


def test_web_analytics_stream_slices(common_params, mocker):
    parent_slicer_mock = mocker.patch("airbyte_cdk.sources.streams.http.HttpSubStream.stream_slices")
    parent_slicer_mock.return_value = (_ for _ in [{"parent": {"id": 1}}])

    pendulum_now_mock = mocker.patch("pendulum.now")
    pendulum_now_mock.return_value = pendulum.parse(common_params["start_date"]).add(days=50)

    stream = ContactsWebAnalytics(**common_params)
    slices = list(stream.stream_slices(SyncMode.incremental, cursor_field="occurredAt"))

    assert len(slices) == 2
    assert all(map(lambda slice: slice["objectId"] == 1, slices))

    assert [("2021-01-10T00:00:00Z", "2021-02-09T00:00:00Z"), ("2021-02-09T00:00:00Z", "2021-03-01T00:00:00Z")] == [
        (s["occurredAfter"], s["occurredBefore"]) for s in slices
    ]


def test_web_analytics_latest_state(common_params, mocker):
    parent_slicer_mock = mocker.patch("airbyte_cdk.sources.streams.http.HttpSubStream.stream_slices")
    parent_slicer_mock.return_value = (_ for _ in [{"parent": {"id": "1"}}])

    pendulum_now_mock = mocker.patch("pendulum.now")
    pendulum_now_mock.return_value = pendulum.parse(common_params["start_date"]).add(days=10)

    parent_slicer_mock = mocker.patch("source_hubspot.streams.BaseStream.read_records")
    parent_slicer_mock.return_value = (_ for _ in [{"objectId": "1", "occurredAt": "2021-01-02T00:00:00Z"}])

    stream = ContactsWebAnalytics(**common_params)
    stream.state = {"1": {"occurredAt": "2021-01-01T00:00:00Z"}}
    slices = list(stream.stream_slices(SyncMode.incremental, cursor_field="occurredAt"))
    records = [
        list(stream.read_records(SyncMode.incremental, cursor_field="occurredAt", stream_slice=stream_slice)) for stream_slice in slices
    ]

    assert len(slices) == 1
    assert len(records) == 1
    assert len(records[0]) == 1
    assert records[0][0]["objectId"] == "1"
    assert stream.state["1"]["occurredAt"] == "2021-01-02T00:00:00Z"


def test_contacts_membership_transform(common_params):
    stream = ContactsListMemberships(**common_params)
    versions = [{"value": "Georgia", "timestamp": 1645135236625}]
    memberships = [{"membership": 1}]
    records = [
        {
            "vid": 1,
            "canonical-vid": 1,
            "portal-id": 1,
            "is-contact": True,
            "properties": {"hs_country": {"versions": versions}, "lastmodifieddate": {"value": 1645135236625}},
            "list-memberships": memberships,
        }
    ]
    assert [{"membership": 1, "canonical-vid": 1} for _ in versions] == list(stream._transform(records=records))


@pytest.mark.parametrize(
    "stream_class, cursor_value, data_to_cast, expected_casted_data",
    [
        ("marketing_emails", {"updated": 1634050455543}, {"rootMicId": 123456}, {"rootMicId": "123456"}),
        ("marketing_emails", {"updated": 1634050455543}, {"rootMicId": None}, {"rootMicId": None}),
        ("marketing_emails", {"updated": 1634050455543}, {"rootMicId": "123456"}, {"rootMicId": "123456"}),
        ("marketing_emails", {"updated": 1634050455543}, {"rootMicId": 1234.56}, {"rootMicId": "1234.56"}),
    ],
)
@mock.patch("source_hubspot.source.SourceHubspot.get_custom_object_streams")
def test_cast_record_fields_with_schema_if_needed(
    mock_get_custom_object_stream, stream_class, cursor_value, requests_mock, common_params, data_to_cast, expected_casted_data, config
):
    """
    Test that the stream cast record fields with stream json schema if needed
    """
    if isinstance(stream_class, str):
        stream = find_stream(stream_class, config)
        data_field = stream.retriever.record_selector.extractor.field_path[0]
    else:
        stream = stream_class(**common_params)
        data_field = stream.data_field

    responses = [
        {
            "json": {
                data_field: [
                    {
                        "id": "test_id",
                        "created": "2022-02-25T16:43:11Z",
                    }
                    | data_to_cast
                    | cursor_value
                ],
            }
        }
    ]

    is_form_submission = isinstance(stream, FormSubmissions)
    stream._sync_mode = SyncMode.full_refresh

    if isinstance(stream_class, str):
        stream_url = stream.retriever.requester.url_base + stream.retriever.requester.path
    else:
        stream_url = stream.url + "/test_id" if is_form_submission else stream.url

    stream._sync_mode = None

    requests_mock.register_uri("GET", stream_url, responses)
    records = read_full_refresh(stream)
    record = records[0]
    print(record)
    for casted_key, casted_value in expected_casted_data.items():
        assert record[casted_key] == casted_value


@pytest.mark.parametrize(
    "stream, endpoint, cursor_value, fake_properties_list_response, data_to_cast, expected_casted_data",
    [
        (
            Deals,
            "deal",
            {"updatedAt": "2022-02-25T16:43:11Z"},
            [("hs_closed_amount", "string")],
            {"hs_closed_amount": 123456},
            {"hs_closed_amount": "123456"},
        ),
        (
            Deals,
            "deal",
            {"updatedAt": "2022-02-25T16:43:11Z"},
            [("hs_closed_amount", "integer")],
            {"hs_closed_amount": "123456"},
            {"hs_closed_amount": 123456},
        ),
        (
            Deals,
            "deal",
            {"updatedAt": "2022-02-25T16:43:11Z"},
            [("hs_closed_amount", "number")],
            {"hs_closed_amount": "123456.10"},
            {"hs_closed_amount": 123456.10},
        ),
        (
            Deals,
            "deal",
            {"updatedAt": "2022-02-25T16:43:11Z"},
            [("hs_closed_amount", "boolean")],
            {"hs_closed_amount": "1"},
            {"hs_closed_amount": True},
        ),
    ],
)
def test_cast_record_fields_if_needed(
    stream, endpoint, cursor_value, fake_properties_list_response, requests_mock, common_params, data_to_cast, expected_casted_data
):
    """
    Test that the stream cast record fields in properties key with properties endpoint response if needed
    """
    stream = stream(**common_params)
    responses = [
        {
            "json": {
                stream.data_field: [{"id": "test_id", "created": "2022-02-25T16:43:11Z", "properties": data_to_cast} | cursor_value],
            }
        }
    ]

    properties_response = [
        {
            "json": [
                {"name": property_name, "type": property_type, "updatedAt": 1571085954360, "createdAt": 1565059306048}
                for property_name, property_type in fake_properties_list_response
            ],
            "status_code": 200,
        }
    ]

    is_form_submission = isinstance(stream, FormSubmissions)
    stream._sync_mode = SyncMode.full_refresh
    stream_url = stream.url + "/test_id" if is_form_submission else stream.url
    stream._sync_mode = None

    requests_mock.register_uri("GET", stream_url, responses)
    requests_mock.register_uri("GET", f"/properties/v2/{endpoint}/properties", properties_response)
    records = read_full_refresh(stream)
    assert records
    record = records[0]
    for casted_key, casted_value in expected_casted_data.items():
        assert record["properties"][casted_key] == casted_value
