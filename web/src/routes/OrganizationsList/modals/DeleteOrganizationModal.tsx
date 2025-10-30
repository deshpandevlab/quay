import {useState} from 'react';
import {Modal, ModalVariant, Button, Text, Alert} from '@patternfly/react-core';
import {useDeleteSingleOrganization} from 'src/hooks/UseOrganizationActions';
import {useAlerts} from 'src/hooks/UseAlerts';
import {AlertVariant} from 'src/atoms/AlertState';

interface DeleteOrganizationModalProps {
  isOpen: boolean;
  onClose: () => void;
  organizationName: string;
}

export default function DeleteOrganizationModal(
  props: DeleteOrganizationModalProps,
) {
  const [error, setError] = useState<string | null>(null);
  const {addAlert} = useAlerts();

  const {deleteOrganization, isLoading} = useDeleteSingleOrganization({
    onSuccess: () => {
      addAlert({
        variant: AlertVariant.Success,
        title: `Successfully deleted organization ${props.organizationName}`,
      });
      handleClose();
    },
    onError: (err) => {
      const errorMessage =
        err?.response?.data?.error_message || 'Failed to delete organization';
      setError(errorMessage);
      addAlert({
        variant: AlertVariant.Failure,
        title: `Failed to delete organization ${props.organizationName}`,
        message: errorMessage,
      });
    },
  });

  const handleClose = () => {
    setError(null);
    props.onClose();
  };

  const handleDelete = () => {
    setError(null);
    deleteOrganization(props.organizationName);
  };

  return (
    <Modal
      title="Delete Organization"
      isOpen={props.isOpen}
      onClose={handleClose}
      variant={ModalVariant.medium}
      actions={[
        <Button
          key="confirm"
          variant="danger"
          onClick={handleDelete}
          isLoading={isLoading}
          isDisabled={isLoading}
        >
          OK
        </Button>,
        <Button key="cancel" variant="link" onClick={handleClose}>
          Cancel
        </Button>,
      ]}
    >
      <Text>
        Are you sure you want to delete this organization? Its data will be
        deleted with it.
      </Text>
      {error && (
        <Alert variant="danger" title="Error" isInline style={{marginTop: 16}}>
          {error}
        </Alert>
      )}
    </Modal>
  );
}
