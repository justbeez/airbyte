/*
 * Copyright (c) 2024 Airbyte, Inc., all rights reserved.
 */

package io.airbyte.integrations.destination.s3_data_lake

import io.airbyte.cdk.ConfigErrorException
import io.airbyte.cdk.load.toolkits.iceberg.parquet.ColumnTypeChangeBehavior
import io.airbyte.cdk.load.toolkits.iceberg.parquet.IcebergSuperTypeFinder
import io.airbyte.cdk.load.toolkits.iceberg.parquet.IcebergTableSynchronizer
import io.airbyte.cdk.load.toolkits.iceberg.parquet.IcebergTypesComparator
import io.airbyte.cdk.load.toolkits.iceberg.parquet.SchemaUpdateResult
import io.mockk.confirmVerified
import io.mockk.every
import io.mockk.just
import io.mockk.mockk
import io.mockk.runs
import io.mockk.spyk
import io.mockk.verify
import org.apache.iceberg.Schema
import org.apache.iceberg.Table
import org.apache.iceberg.UpdateSchema
import org.apache.iceberg.types.Type.PrimitiveType
import org.apache.iceberg.types.Types
import org.assertj.core.api.Assertions.assertThat
import org.assertj.core.api.Assertions.assertThatThrownBy
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test

/**
 * Tests for [IcebergTableSynchronizer].
 *
 * We use a mocked [Table] and [UpdateSchema] to verify that the right calls are made based on the
 * computed [IcebergTypesComparator.ColumnDiff].
 */
class S3DataLakeTableSynchronizerTest {

    // Mocks
    private lateinit var mockTable: Table
    private lateinit var mockUpdateSchema: UpdateSchema
    private lateinit var mockNewSchema: Schema

    // Collaborators under test
    private val comparator = spyk(IcebergTypesComparator())
    private val superTypeFinder = spyk(IcebergSuperTypeFinder(comparator))
    private val synchronizer = IcebergTableSynchronizer(comparator, superTypeFinder)

    @BeforeEach
    fun setUp() {
        // Prepare the mocks before each test
        mockTable = mockk(relaxed = true)
        mockUpdateSchema = mockk(relaxed = true)
        mockNewSchema = mockk(relaxed = true)

        // By default, let table.schema() return an empty schema. Tests can override this as needed.
        every { mockTable.schema() } returns Schema(listOf())

        // Table.updateSchema() should return the mock UpdateSchema
        every { mockTable.updateSchema().allowIncompatibleChanges() } returns mockUpdateSchema

        // apply should return a fake schema
        every { mockUpdateSchema.apply() } returns mockNewSchema

        // No-op for the commit call unless specifically tested for. We'll verify calls later.
        every { mockUpdateSchema.commit() } just runs
    }

    /** Helper to build a schema with [Types.NestedField]s. */
    private fun buildSchema(
        vararg fields: Types.NestedField,
        identifierFields: Set<Int> = emptySet()
    ): Schema {
        return Schema(fields.toList(), identifierFields)
    }

    @Test
    fun `test no changes - should do nothing`() {
        // The existing schema is the same as incoming => no diffs
        val existingSchema =
            buildSchema(Types.NestedField.required(1, "id", Types.IntegerType.get()))
        existingSchema.identifierFieldNames()
        val incomingSchema =
            buildSchema(Types.NestedField.required(1, "id", Types.IntegerType.get()))

        every { mockTable.schema() } returns existingSchema
        // The comparator will see no changes
        every { comparator.compareSchemas(incomingSchema, existingSchema) } answers
            {
                IcebergTypesComparator.ColumnDiff()
            }

        val result =
            synchronizer.maybeApplySchemaChanges(
                mockTable,
                incomingSchema,
                ColumnTypeChangeBehavior.SAFE_SUPERTYPE
            )

        // We expect the original schema to be returned
        assertThat(result).isEqualTo(SchemaUpdateResult(existingSchema, pendingUpdate = null))

        // Verify that no calls to updateSchema() manipulation were made
        verify(exactly = 0) { mockUpdateSchema.deleteColumn(any()) }
        verify(exactly = 0) { mockUpdateSchema.updateColumn(any(), any<PrimitiveType>()) }
        verify(exactly = 0) { mockUpdateSchema.makeColumnOptional(any()) }
        verify(exactly = 0) { mockUpdateSchema.addColumn(any<String>(), any<String>(), any()) }
        verify(exactly = 0) { mockUpdateSchema.setIdentifierFields(any<Collection<String>>()) }
        verify(exactly = 0) { mockUpdateSchema.commit() }
        verify(exactly = 0) { mockTable.refresh() }
    }

    @Test
    fun `test remove columns`() {
        val existingSchema =
            buildSchema(Types.NestedField.optional(1, "remove_me", Types.StringType.get()))
        val incomingSchema = buildSchema() // empty => remove everything

        every { mockTable.schema() } returns existingSchema

        val result =
            synchronizer.maybeApplySchemaChanges(
                mockTable,
                incomingSchema,
                ColumnTypeChangeBehavior.SAFE_SUPERTYPE
            )

        // The result is a new schema after changes, but we can only verify calls on the mock
        // Here we expect remove_me to be deleted.
        verify { mockUpdateSchema.deleteColumn("remove_me") }
        verify { mockUpdateSchema.commit() }

        // The final returned schema is the table's schema after refresh
        // Since we aren't actually applying changes, just assert that it's whatever the mock
        // returns
        assertThat(result).isEqualTo(SchemaUpdateResult(mockNewSchema, pendingUpdate = null))
    }

    @Test
    fun `test update data type to supertype`() {
        val existingSchema =
            buildSchema(Types.NestedField.optional(2, "age", Types.IntegerType.get()))
        val incomingSchema = buildSchema(Types.NestedField.optional(2, "age", Types.LongType.get()))

        every { mockTable.schema() } returns existingSchema

        // Apply changes
        synchronizer.maybeApplySchemaChanges(
            mockTable,
            incomingSchema,
            ColumnTypeChangeBehavior.SAFE_SUPERTYPE
        )

        // Verify that "age" is updated to LONG
        verify { mockUpdateSchema.updateColumn("age", Types.LongType.get()) }
        // And that changes are committed
        verify { mockUpdateSchema.commit() }
    }

    @Test
    fun `test newly optional columns`() {
        val existingSchema =
            buildSchema(Types.NestedField.required(3, "make_optional", Types.StringType.get()))
        val incomingSchema =
            buildSchema(Types.NestedField.optional(3, "make_optional", Types.StringType.get()))

        every { mockTable.schema() } returns existingSchema

        synchronizer.maybeApplySchemaChanges(
            mockTable,
            incomingSchema,
            ColumnTypeChangeBehavior.SAFE_SUPERTYPE
        )

        // We expect makeColumnOptional("make_optional") to be called
        verify { mockUpdateSchema.makeColumnOptional("make_optional") }
        verify { mockUpdateSchema.commit() }
    }

    @Test
    fun `test add new columns - top level`() {
        val existingSchema =
            buildSchema(Types.NestedField.required(1, "id", Types.IntegerType.get()))
        val incomingSchema =
            buildSchema(
                Types.NestedField.required(1, "id", Types.IntegerType.get()),
                Types.NestedField.optional(2, "new_col", Types.StringType.get()),
            )

        every { mockTable.schema() } returns existingSchema

        synchronizer.maybeApplySchemaChanges(
            mockTable,
            incomingSchema,
            ColumnTypeChangeBehavior.SAFE_SUPERTYPE
        )

        verify { mockUpdateSchema.addColumn(null, "new_col", Types.StringType.get()) }
        verify { mockUpdateSchema.commit() }
    }

    @Test
    fun `test add new columns - nested one-level`() {
        val existingSchema =
            buildSchema(
                Types.NestedField.required(
                    1,
                    "user_info",
                    Types.StructType.of(
                        Types.NestedField.required(2, "nested_id", Types.IntegerType.get())
                    )
                )
            )
        val incomingSchema =
            buildSchema(
                Types.NestedField.required(
                    1,
                    "user_info",
                    Types.StructType.of(
                        Types.NestedField.required(2, "nested_id", Types.IntegerType.get()),
                        // new subfield
                        Types.NestedField.optional(3, "nested_name", Types.StringType.get()),
                    )
                )
            )

        every { mockTable.schema() } returns existingSchema

        // For the newly added leaf "nested_name"
        // We'll also ensure that the subfield is found
        val userInfoStruct = incomingSchema.findField("user_info")!!.type().asStructType()
        val nestedNameField = userInfoStruct.asSchema().findField("nested_name")
        assertThat(nestedNameField).isNotNull // Just a sanity check in the test

        synchronizer.maybeApplySchemaChanges(
            mockTable,
            incomingSchema,
            ColumnTypeChangeBehavior.SAFE_SUPERTYPE
        )

        verify { mockUpdateSchema.addColumn("user_info", "nested_name", Types.StringType.get()) }
        verify { mockUpdateSchema.commit() }
    }

    @Test
    fun `test add new columns - more than one-level nesting throws`() {
        // e.g. "outer~inner~leaf" is two levels
        val existingSchema = buildSchema()
        val incomingSchema = buildSchema() // Not too relevant, since we expect an exception

        every { mockTable.schema() } returns existingSchema
        val diff = IcebergTypesComparator.ColumnDiff(newColumns = mutableListOf("outer~inner~leaf"))
        every { comparator.compareSchemas(incomingSchema, existingSchema) } returns diff

        assertThatThrownBy {
                synchronizer.maybeApplySchemaChanges(
                    mockTable,
                    incomingSchema,
                    ColumnTypeChangeBehavior.SAFE_SUPERTYPE
                )
            }
            .isInstanceOf(ConfigErrorException::class.java)
            .hasMessageContaining("Adding nested columns more than 1 level deep is not supported")

        // No calls to commit
        verify(exactly = 0) { mockUpdateSchema.commit() }
        verify(exactly = 0) { mockTable.refresh() }
    }

    @Test
    fun `test update with non-primitive supertype throws`() {
        // Suppose the comparator says that "complex_col" has an updated data type
        // but the superTypeFinder returns a struct (non-primitive).
        val existingSchema =
            buildSchema(Types.NestedField.required(10, "complex_col", Types.StructType.of()))
        val incomingSchema =
            buildSchema(Types.NestedField.required(10, "complex_col", Types.StructType.of()))

        every { mockTable.schema() } returns existingSchema
        val diff =
            IcebergTypesComparator.ColumnDiff(updatedDataTypes = mutableListOf("complex_col"))
        every { comparator.compareSchemas(incomingSchema, existingSchema) } returns diff

        // Let superTypeFinder return a struct type
        val structType =
            Types.StructType.of(Types.NestedField.optional(1, "field", Types.StringType.get()))
        every { superTypeFinder.findSuperType(any(), any(), "complex_col") } returns structType

        assertThatThrownBy {
                synchronizer.maybeApplySchemaChanges(
                    mockTable,
                    incomingSchema,
                    ColumnTypeChangeBehavior.SAFE_SUPERTYPE
                )
            }
            .isInstanceOf(ConfigErrorException::class.java)
            .hasMessageContaining("Currently only primitive type updates are supported.")

        // No updates or commits
        verify(exactly = 0) { mockUpdateSchema.updateColumn(any(), any<PrimitiveType>()) }
        verify(exactly = 0) { mockUpdateSchema.commit() }
        verify(exactly = 0) { mockTable.refresh() }
    }

    @Test
    fun `test update identifier fields`() {
        val existingSchema =
            buildSchema(Types.NestedField.required(3, "id", Types.StringType.get()))
        val incomingSchema =
            buildSchema(
                Types.NestedField.required(3, "id", Types.StringType.get()),
                identifierFields = setOf(3)
            )

        every { mockTable.schema() } returns existingSchema

        synchronizer.maybeApplySchemaChanges(
            mockTable,
            incomingSchema,
            ColumnTypeChangeBehavior.SAFE_SUPERTYPE
        )

        // We expect setIdentifierFields(listOf("id")) to be called
        verify { mockUpdateSchema.requireColumn("id") }
        verify { mockUpdateSchema.setIdentifierFields(listOf("id")) }
        verify { mockUpdateSchema.commit() }
    }

    @Test
    fun `test multiple operations in one pass`() {
        val existingSchema =
            buildSchema(
                Types.NestedField.required(1, "id", Types.IntegerType.get()),
                Types.NestedField.optional(2, "remove_me", Types.StringType.get()),
                Types.NestedField.required(3, "make_optional", Types.IntegerType.get()),
                Types.NestedField.required(4, "upgrade_int", Types.IntegerType.get())
            )
        val incomingSchema =
            buildSchema(
                // "remove_me" is gone -> removal
                Types.NestedField.required(1, "id", Types.IntegerType.get()),
                // make_optional -> newly optional
                Types.NestedField.optional(3, "make_optional", Types.IntegerType.get()),
                // upgrade_int -> changed to long
                Types.NestedField.required(4, "upgrade_int", Types.LongType.get()),
                // brand_new -> new column
                Types.NestedField.optional(5, "brand_new", Types.FloatType.get()),
                identifierFields = setOf(1)
            )

        every { mockTable.schema() } returns existingSchema

        // Suppose superTypeFinder says int->long is valid
        every {
            superTypeFinder.findSuperType(
                Types.IntegerType.get(),
                Types.LongType.get(),
                "upgrade_int"
            )
        } returns Types.LongType.get()

        synchronizer.maybeApplySchemaChanges(
            mockTable,
            incomingSchema,
            ColumnTypeChangeBehavior.SAFE_SUPERTYPE
        )

        // Verify calls, in any order
        verify { mockUpdateSchema.deleteColumn("remove_me") }
        verify { mockUpdateSchema.updateColumn("upgrade_int", Types.LongType.get()) }
        verify { mockUpdateSchema.makeColumnOptional("make_optional") }
        verify { mockUpdateSchema.addColumn(null, "brand_new", Types.FloatType.get()) }
        verify { mockUpdateSchema.requireColumn("id") }
        verify { mockUpdateSchema.setIdentifierFields(listOf("id")) }

        verify { mockUpdateSchema.commit() }
    }

    @Test
    fun `test fail on incompatible type change`() {
        val existingSchema =
            buildSchema(Types.NestedField.optional(2, "age", Types.IntegerType.get()))
        val incomingSchema =
            buildSchema(Types.NestedField.optional(2, "age", Types.StringType.get()))

        every { mockTable.schema() } returns existingSchema

        assertThatThrownBy {
                synchronizer.maybeApplySchemaChanges(
                    mockTable,
                    incomingSchema,
                    ColumnTypeChangeBehavior.SAFE_SUPERTYPE
                )
            }
            .isInstanceOf(ConfigErrorException::class.java)
            .hasMessage(
                """Schema evolution for column "age" between int and string is not allowed."""
            )
    }

    @Test
    fun `test overwrite on incompatible type change`() {
        val existingSchema =
            buildSchema(Types.NestedField.optional(2, "age", Types.IntegerType.get()))
        val incomingSchema =
            buildSchema(Types.NestedField.optional(2, "age", Types.StringType.get()))

        every { mockTable.schema() } returns existingSchema

        val (schema, pendingUpdate) =
            synchronizer.maybeApplySchemaChanges(
                mockTable,
                incomingSchema,
                ColumnTypeChangeBehavior.OVERWRITE
            )

        verify { mockUpdateSchema.deleteColumn("age") }
        verify { mockUpdateSchema.addColumn("age", Types.StringType.get()) }
        verify(exactly = 0) { mockUpdateSchema.commit() }
        // reminder: apply() doesn't actually make any changes, it just verifies
        // that the schema change is valid
        verify { mockUpdateSchema.apply() }
        confirmVerified(mockUpdateSchema)

        assertThat(schema).isSameAs(mockNewSchema)
        assertThat(pendingUpdate).isNotNull
    }
}
