# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: my.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='my.proto',
  package='',
  syntax='proto3',
  serialized_options=None,
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n\x08my.proto\"\xb7\x02\n\x13\x43ontinuationCommand\x12)\n\x05\x65ntry\x18\x32 \x01(\x0b\x32\x1a.ContinuationCommand.Entry\x1a\xf4\x01\n\x05\x45ntry\x12\x33\n\x07\x64\x65tails\x18\x0c \x01(\x0b\x32\".ContinuationCommand.Entry.Details\x1a\xb5\x01\n\x07\x44\x65tails\x12\x10\n\x08targetId\x18\x01 \x01(\t\x12\x13\n\x0b\x63hannelType\x18\x02 \x01(\x05\x12I\n\x0e\x63hannelDetails\x18\x03 \x01(\x0b\x32\x31.ContinuationCommand.Entry.Details.ChannelDetails\x1a\x38\n\x0e\x43hannelDetails\x12\x13\n\x0b\x63hannelType\x18\x01 \x01(\x05\x12\x11\n\tchannelId\x18\x02 \x01(\t\"\x8a\x01\n\x18\x43ontinuationCommandEntry\x12\x31\n\x05\x65ntry\x18\x9c\xd5\xa0& \x01(\x0b\x32\x1f.ContinuationCommandEntry.Entry\x1a;\n\x05\x45ntry\x12\x0f\n\x07\x63ommand\x18\x02 \x01(\t\x12\x0f\n\x07\x64\x65tails\x18\x03 \x01(\t\x12\x10\n\x08targetId\x18# \x01(\tb\x06proto3'
)




_CONTINUATIONCOMMAND_ENTRY_DETAILS_CHANNELDETAILS = _descriptor.Descriptor(
  name='ChannelDetails',
  full_name='ContinuationCommand.Entry.Details.ChannelDetails',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='channelType', full_name='ContinuationCommand.Entry.Details.ChannelDetails.channelType', index=0,
      number=1, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='channelId', full_name='ContinuationCommand.Entry.Details.ChannelDetails.channelId', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=268,
  serialized_end=324,
)

_CONTINUATIONCOMMAND_ENTRY_DETAILS = _descriptor.Descriptor(
  name='Details',
  full_name='ContinuationCommand.Entry.Details',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='targetId', full_name='ContinuationCommand.Entry.Details.targetId', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='channelType', full_name='ContinuationCommand.Entry.Details.channelType', index=1,
      number=2, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='channelDetails', full_name='ContinuationCommand.Entry.Details.channelDetails', index=2,
      number=3, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[_CONTINUATIONCOMMAND_ENTRY_DETAILS_CHANNELDETAILS, ],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=143,
  serialized_end=324,
)

_CONTINUATIONCOMMAND_ENTRY = _descriptor.Descriptor(
  name='Entry',
  full_name='ContinuationCommand.Entry',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='details', full_name='ContinuationCommand.Entry.details', index=0,
      number=12, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[_CONTINUATIONCOMMAND_ENTRY_DETAILS, ],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=80,
  serialized_end=324,
)

_CONTINUATIONCOMMAND = _descriptor.Descriptor(
  name='ContinuationCommand',
  full_name='ContinuationCommand',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='entry', full_name='ContinuationCommand.entry', index=0,
      number=50, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[_CONTINUATIONCOMMAND_ENTRY, ],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=13,
  serialized_end=324,
)


_CONTINUATIONCOMMANDENTRY_ENTRY = _descriptor.Descriptor(
  name='Entry',
  full_name='ContinuationCommandEntry.Entry',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='command', full_name='ContinuationCommandEntry.Entry.command', index=0,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='details', full_name='ContinuationCommandEntry.Entry.details', index=1,
      number=3, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='targetId', full_name='ContinuationCommandEntry.Entry.targetId', index=2,
      number=35, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=406,
  serialized_end=465,
)

_CONTINUATIONCOMMANDENTRY = _descriptor.Descriptor(
  name='ContinuationCommandEntry',
  full_name='ContinuationCommandEntry',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='entry', full_name='ContinuationCommandEntry.entry', index=0,
      number=80226972, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[_CONTINUATIONCOMMANDENTRY_ENTRY, ],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=327,
  serialized_end=465,
)

_CONTINUATIONCOMMAND_ENTRY_DETAILS_CHANNELDETAILS.containing_type = _CONTINUATIONCOMMAND_ENTRY_DETAILS
_CONTINUATIONCOMMAND_ENTRY_DETAILS.fields_by_name['channelDetails'].message_type = _CONTINUATIONCOMMAND_ENTRY_DETAILS_CHANNELDETAILS
_CONTINUATIONCOMMAND_ENTRY_DETAILS.containing_type = _CONTINUATIONCOMMAND_ENTRY
_CONTINUATIONCOMMAND_ENTRY.fields_by_name['details'].message_type = _CONTINUATIONCOMMAND_ENTRY_DETAILS
_CONTINUATIONCOMMAND_ENTRY.containing_type = _CONTINUATIONCOMMAND
_CONTINUATIONCOMMAND.fields_by_name['entry'].message_type = _CONTINUATIONCOMMAND_ENTRY
_CONTINUATIONCOMMANDENTRY_ENTRY.containing_type = _CONTINUATIONCOMMANDENTRY
_CONTINUATIONCOMMANDENTRY.fields_by_name['entry'].message_type = _CONTINUATIONCOMMANDENTRY_ENTRY
DESCRIPTOR.message_types_by_name['ContinuationCommand'] = _CONTINUATIONCOMMAND
DESCRIPTOR.message_types_by_name['ContinuationCommandEntry'] = _CONTINUATIONCOMMANDENTRY
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

ContinuationCommand = _reflection.GeneratedProtocolMessageType('ContinuationCommand', (_message.Message,), {

  'Entry' : _reflection.GeneratedProtocolMessageType('Entry', (_message.Message,), {

    'Details' : _reflection.GeneratedProtocolMessageType('Details', (_message.Message,), {

      'ChannelDetails' : _reflection.GeneratedProtocolMessageType('ChannelDetails', (_message.Message,), {
        'DESCRIPTOR' : _CONTINUATIONCOMMAND_ENTRY_DETAILS_CHANNELDETAILS,
        '__module__' : 'my_pb2'
        # @@protoc_insertion_point(class_scope:ContinuationCommand.Entry.Details.ChannelDetails)
        })
      ,
      'DESCRIPTOR' : _CONTINUATIONCOMMAND_ENTRY_DETAILS,
      '__module__' : 'my_pb2'
      # @@protoc_insertion_point(class_scope:ContinuationCommand.Entry.Details)
      })
    ,
    'DESCRIPTOR' : _CONTINUATIONCOMMAND_ENTRY,
    '__module__' : 'my_pb2'
    # @@protoc_insertion_point(class_scope:ContinuationCommand.Entry)
    })
  ,
  'DESCRIPTOR' : _CONTINUATIONCOMMAND,
  '__module__' : 'my_pb2'
  # @@protoc_insertion_point(class_scope:ContinuationCommand)
  })
_sym_db.RegisterMessage(ContinuationCommand)
_sym_db.RegisterMessage(ContinuationCommand.Entry)
_sym_db.RegisterMessage(ContinuationCommand.Entry.Details)
_sym_db.RegisterMessage(ContinuationCommand.Entry.Details.ChannelDetails)

ContinuationCommandEntry = _reflection.GeneratedProtocolMessageType('ContinuationCommandEntry', (_message.Message,), {

  'Entry' : _reflection.GeneratedProtocolMessageType('Entry', (_message.Message,), {
    'DESCRIPTOR' : _CONTINUATIONCOMMANDENTRY_ENTRY,
    '__module__' : 'my_pb2'
    # @@protoc_insertion_point(class_scope:ContinuationCommandEntry.Entry)
    })
  ,
  'DESCRIPTOR' : _CONTINUATIONCOMMANDENTRY,
  '__module__' : 'my_pb2'
  # @@protoc_insertion_point(class_scope:ContinuationCommandEntry)
  })
_sym_db.RegisterMessage(ContinuationCommandEntry)
_sym_db.RegisterMessage(ContinuationCommandEntry.Entry)


# @@protoc_insertion_point(module_scope)